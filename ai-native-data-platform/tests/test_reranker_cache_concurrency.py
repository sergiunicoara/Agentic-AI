"""Regression test: the MMR/cross-encoder rerankers' module-level embedding
caches must be safe under concurrent access — same class of bug as
tests/test_cache_concurrency.py's InMemoryLRU race (this is the identical
get/evict/set pattern, duplicated across both reranker modules). FastAPI
runs sync routes, including reranking, in a shared threadpool.
"""
from __future__ import annotations

import sys
import threading

import pytest

import app.retrieval.rerankers.cross_encoder_stub as cross_encoder_stub
import app.retrieval.rerankers.mmr as mmr


@pytest.mark.parametrize("module", [mmr, cross_encoder_stub])
def test_concurrent_cache_get_set_never_raises_or_exceeds_capacity(module):
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.00001)
    try:
        module._EMB_CACHE.clear()
        module._EMB_CACHE_MAX = 50
        exceptions: list[str] = []

        def worker(base: int) -> None:
            for i in range(300):
                try:
                    module._cache_set("v1", f"c{base}-{i}", [0.1, 0.2, 0.3])
                    module._cache_get("v1", f"c{base}-{i}")
                except Exception as e:  # pragma: no cover - only on regression
                    exceptions.append(f"{type(e).__name__}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(16)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert exceptions == [], f"concurrent access raised: {exceptions[:5]}"
        assert len(module._EMB_CACHE) <= module._EMB_CACHE_MAX
    finally:
        sys.setswitchinterval(original_interval)
        module._EMB_CACHE.clear()
