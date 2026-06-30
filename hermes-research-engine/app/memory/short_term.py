"""Sliding-window short-term memory with token-budget enforcement."""
from __future__ import annotations

from typing import List

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")
_DEFAULT_BUDGET = 6000  # tokens kept in context per agent


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text, disallowed_special=()))


class SlidingWindowMemory:
    """Keeps the system message + as many recent messages as fit within token_budget."""

    def __init__(self, token_budget: int = _DEFAULT_BUDGET) -> None:
        self.token_budget = token_budget
        self._system: dict | None = None
        self._messages: List[dict] = []

    def set_system(self, content: str) -> None:
        self._system = {"role": "system", "content": content}

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})

    def get_window(self) -> List[dict]:
        """Return system + most-recent messages that fit in the token budget."""
        budget = self.token_budget
        if self._system:
            budget -= _count_tokens(self._system["content"])

        window: List[dict] = []
        for msg in reversed(self._messages):
            cost = _count_tokens(msg["content"])
            if budget - cost < 0:
                break
            window.insert(0, msg)
            budget -= cost

        result = []
        if self._system:
            result.append(self._system)
        result.extend(window)
        return result

    def total_tokens(self) -> int:
        msgs = self.get_window()
        return sum(_count_tokens(m["content"]) for m in msgs)

    def clear(self) -> None:
        self._messages = []
