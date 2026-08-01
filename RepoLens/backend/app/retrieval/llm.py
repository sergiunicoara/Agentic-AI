import re
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Protocol

from anthropic import AsyncAnthropic

try:
    from langfuse import observe
except ImportError:  # pragma: no cover - dependency is installed in runtime images
    observe = None

from app.config import get_settings
from app.retrieval.models import ChatTurn


def _langfuse_observe(*args, **kwargs):
    settings = get_settings()
    if observe is None or not (settings.langfuse_public_key and settings.langfuse_secret_key):
        def decorator(function):
            return function

        return decorator
    return observe(*args, **kwargs)

SYSTEM_PROMPT = (
    "You are a code documentation assistant. Answer questions about the provided "
    "codebase using ONLY the context blocks below. Factual claims supported by the "
    "context should be followed by a citation in the exact form [path/to/file:start-end], copied "
    "verbatim from the header of the context block it came from. If the provided "
    "context does not contain enough information to answer the question, say so "
    "plainly instead of guessing — do not speculate beyond what the context shows."
)


class LLMClient(Protocol):
    def stream_reply(
        self, system: str, history: list[ChatTurn], context: str, question: str
    ) -> AsyncIterator[str]: ...

    async def complete(self, prompt: str) -> str:
        """One-shot, non-streaming completion — used by the eval judge, which needs
        a single scored response rather than a conversational stream."""
        ...


class AnthropicClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model

    @_langfuse_observe(name="anthropic.stream_reply", as_type="generation")
    async def stream_reply(
        self, system: str, history: list[ChatTurn], context: str, question: str
    ) -> AsyncIterator[str]:
        messages = [{"role": turn.role, "content": turn.content} for turn in history]
        messages.append(
            {"role": "user", "content": f"Context:\n\n{context}\n\nQuestion: {question}"}
        )

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @_langfuse_observe(name="anthropic.complete", as_type="generation")
    async def complete(self, prompt: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    async def aclose(self) -> None:
        await self._client.close()


@lru_cache
def get_anthropic_client() -> AnthropicClient:
    return AnthropicClient()


async def close_anthropic_client() -> None:
    if get_anthropic_client.cache_info().currsize:
        await get_anthropic_client().aclose()
        get_anthropic_client.cache_clear()


_CITATION_HEADER_RE = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)


class FakeLLMClient:
    """Deterministic offline LLM used in tests. Echoes a canned answer that cites the
    first context block it's given, so orchestration/citation-parsing is testable
    without a real API key or network access. Records the last call for assertions."""

    def __init__(self, canned_answer: str | None = None, canned_completion: str = "1.0") -> None:
        self.canned_answer = canned_answer
        self.canned_completion = canned_completion
        self.last_call: dict[str, object] | None = None
        self.last_prompt: str | None = None

    async def stream_reply(
        self, system: str, history: list[ChatTurn], context: str, question: str
    ) -> AsyncIterator[str]:
        self.last_call = {
            "system": system,
            "history": history,
            "context": context,
            "question": question,
        }
        answer = self.canned_answer or self._default_answer(context)
        for word in answer.split(" "):
            yield word + " "

    async def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.canned_completion

    @staticmethod
    def _default_answer(context: str) -> str:
        match = _CITATION_HEADER_RE.search(context)
        citation = f"[{match.group(1)}]" if match else "[unknown:0-0]"
        return f"Based on the provided context, here is the answer. {citation}"
