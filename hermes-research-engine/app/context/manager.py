"""Context manager: token budget enforcement + semantic cache."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Optional

from app.memory.long_term import long_term_memory

_CACHE_SIM_THRESHOLD = 0.95
_CACHE_TABLE = "semantic_cache"


class ContextManager:
    """
    Enforces per-request token budgets and short-circuits LLM calls
    when a semantically identical query was recently answered.
    """

    def __init__(self, total_budget: int = 20_000) -> None:
        self.total_budget = total_budget
        self._used: int = 0
        self._cache: Dict[str, dict] = {}  # in-process cache

    def consume(self, tokens: int) -> bool:
        """Returns False if budget exceeded."""
        if self._used + tokens > self.total_budget:
            return False
        self._used += tokens
        return True

    def remaining(self) -> int:
        return max(0, self.total_budget - self._used)

    def cache_lookup(self, query: str) -> Optional[str]:
        """Return cached answer if a near-identical query exists (cosine ≥ 0.95)."""
        key = hashlib.md5(query.encode()).hexdigest()
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["ts"] < 3600:  # 1-hour TTL
                return entry["answer"]

        # Vector similarity check against long-term memory cache entries
        try:
            results = long_term_memory.search(f"CACHE:{query}", k=1)
            for r in results:
                if r["source"] == "cache":
                    score = long_term_memory.similarity_score(query, r["text"].replace("CACHE:", ""))
                    if score >= _CACHE_SIM_THRESHOLD:
                        return r.get("answer", None)
        except Exception:
            pass
        return None

    def cache_store(self, query: str, answer: str) -> None:
        key = hashlib.md5(query.encode()).hexdigest()
        self._cache[key] = {"answer": answer, "ts": time.time()}


context_manager = ContextManager()
