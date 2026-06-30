"""
BaseHermesAgent: ReAct loop using native OpenAI tool-calling format.
Works with Groq, HuggingFace, Together, or any OpenAI-compatible provider.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from openai import OpenAI

from app.observability import logger, RequestMetrics

_MODEL = os.getenv("HERMES_MODEL", "llama-3.1-8b-instant")
_BASE_URL = os.getenv("HF_BASE_URL", "https://api.groq.com/openai/v1")
_MAX_STEPS = 4


def _build_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["HF_TOKEN"],
        base_url=_BASE_URL,
    )


class BaseHermesAgent:
    """
    Single agent with:
    - ReAct loop via native OpenAI tool calling (works with Groq/Llama/Hermes)
    - Structured observability (trace_id, tokens, latency)
    """

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        tools: List[dict],
        tool_handlers: Dict[str, Callable[..., Any]],
        metrics: Optional[RequestMetrics] = None,
        token_budget: int = 6000,
    ) -> None:
        self.agent_id = agent_id
        self.tools = tools
        self.tool_handlers = tool_handlers
        self.metrics = metrics
        self._client = _build_client()
        self._messages: List[dict] = []
        self._system = system_prompt

    def _get_messages(self) -> List[dict]:
        msgs = [{"role": "system", "content": self._system}]
        msgs.extend(self._messages)
        return msgs

    def _call_llm(self, trace_id: str):
        t0 = time.perf_counter()
        kwargs = dict(
            model=_MODEL,
            messages=self._get_messages(),
            temperature=0.2,
            max_tokens=1024,
        )
        if self.tools:
            kwargs["tools"] = self.tools
            kwargs["tool_choice"] = "auto"
        else:
            kwargs["tool_choice"] = "none"
        resp = self._client.chat.completions.create(**kwargs)
        latency = (time.perf_counter() - t0) * 1000
        usage = resp.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        if self.metrics:
            self.metrics.add_llm(tokens_in, tokens_out, latency)

        logger.step(
            trace_id=trace_id,
            agent_id=self.agent_id,
            event="llm_call",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
        )
        return resp.choices[0].message

    def _dispatch_tool(self, trace_id: str, name: str, arguments: str) -> str:
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {}

        handler = self.tool_handlers.get(name)
        if not handler:
            return f"Error: unknown tool '{name}'"
        try:
            result = handler(**args)
        except Exception as exc:
            result = f"Error: {exc}"

        result_str = json.dumps(result) if not isinstance(result, str) else result
        logger.tool_call(trace_id, self.agent_id, name, args, len(result_str))
        if self.metrics:
            self.metrics.add_tool()
        return result_str

    def run(self, user_message: str, trace_id: str) -> str:
        self._messages.append({"role": "user", "content": user_message})

        for _ in range(_MAX_STEPS):
            message = self._call_llm(trace_id)

            if not message.tool_calls:
                content = message.content or ""
                self._messages.append({"role": "assistant", "content": content})
                return content

            # Add assistant message — only keep fields the API accepts
            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ]
            self._messages.append(assistant_msg)

            for tc in message.tool_calls:
                observation = self._dispatch_tool(trace_id, tc.function.name, tc.function.arguments)
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                })

        return "Max reasoning steps reached."

    async def stream(self, user_message: str, trace_id: str) -> AsyncGenerator[str, None]:
        self._messages.append({"role": "user", "content": user_message})

        for step in range(_MAX_STEPS):
            message = self._call_llm(trace_id)

            if not message.tool_calls:
                content = message.content or ""
                self._messages.append({"role": "assistant", "content": content})
                yield json.dumps({"type": "final_answer", "content": content})
                return

            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ]
            self._messages.append(assistant_msg)
            yield json.dumps({"type": "thought", "step": step, "content": message.content or ""})

            for tc in message.tool_calls:
                yield json.dumps({"type": "tool_call", "tool": tc.function.name, "args": tc.function.arguments})
                observation = self._dispatch_tool(trace_id, tc.function.name, tc.function.arguments)
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                })
                yield json.dumps({"type": "observation", "tool": tc.function.name, "result": observation[:500]})

        yield json.dumps({"type": "error", "content": "Max reasoning steps reached."})
