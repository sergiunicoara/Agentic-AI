#!/usr/bin/env python3
"""
Minimal example: a fake agent that emits events to the observability dashboard.

Run after `docker compose up`:
    pip install -e ./sdk
    python sdk/examples/simple_agent.py
"""

import asyncio
import random
import time

from agent_observability import AgentTracer


async def fake_llm_call(prompt: str) -> tuple[str, int, int]:
    """Simulates an LLM call with random latency and token counts."""
    await asyncio.sleep(random.uniform(0.1, 0.6))
    return "I am a simulated response.", random.randint(50, 300), random.randint(20, 150)


async def fake_tool_call(tool_name: str) -> str:
    await asyncio.sleep(random.uniform(0.05, 0.2))
    return f"{tool_name} result"


async def run_agent(tracer: AgentTracer, task_id: str) -> None:
    print(f"[agent] Starting task {task_id}")

    async with tracer.trace(task_id) as trace:
        # LLM call span
        async with trace.span("llm_call", model="claude-sonnet-4-6") as span:
            result, in_tok, out_tok = await fake_llm_call("Summarise the weather report.")
            span.record_tokens(input=in_tok, output=out_tok)
            span.set_attribute("prompt_length", str(len("Summarise the weather report.")))
            print(f"[agent] LLM response: {result[:40]}…  tokens={in_tok}↑{out_tok}↓")

        # Tool call span
        async with trace.span("tool_call") as span:
            tool_result = await fake_tool_call("web_search")
            span.set_attribute("tool", "web_search")
            span.set_attribute("result_length", str(len(tool_result)))
            print(f"[agent] Tool result: {tool_result}")

        # Second LLM call
        async with trace.span("llm_call", model="claude-haiku-4-5") as span:
            _, in_tok2, out_tok2 = await fake_llm_call("Synthesise findings.")
            span.record_tokens(input=in_tok2, output=out_tok2)

        trace.set_outcome("success")

    print(f"[agent] Task {task_id} complete")


async def main() -> None:
    async with AgentTracer(server="localhost:50051", agent_name="weather-agent") as tracer:
        tasks = [f"task-{i:04d}" for i in range(5)]
        for task_id in tasks:
            await run_agent(tracer, task_id)
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
