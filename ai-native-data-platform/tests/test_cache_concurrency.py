"""Regression test: InMemoryLRU must be safe under concurrent access.

FastAPI runs sync routes in a shared threadpool, so cache.get_json /
cache.set_json (used on every /ask, via the retrieval pipeline's result
cache) are called from multiple OS threads concurrently whenever Redis is
unset or unreachable — exactly when this in-process fallback is in use.
The unlocked version raced: `move_to_end(key)` in one thread's set() could
run after another thread's concurrent set() had already evicted that same
key via `popitem(last=False)`, raising a real KeyError. That KeyError was
unguarded all the way up through Cache.get_json/set_json into the
retrieval pipeline's cache calls — a crash under concurrent load with no
Redis, not just a "theoretical" race.

Confirmed empirically before the fix: with sys.setswitchinterval lowered
to widen the race window, 24 threads doing 500 set()+get() calls each
raised real KeyErrors on the unlocked implementation (0 capacity
violations, but ~1000+ raised KeyErrors per run). This test pins the fix.
"""
from __future__ import annotations

import sys
import threading

from app.core.cache import InMemoryLRU


def test_concurrent_set_and_get_never_raises_or_exceeds_capacity():
    # Widen the race window as far as possible — this is what made the
    # unlocked version's KeyError reproducible in the first place.
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.00001)
    try:
        lru = InMemoryLRU(max_items=50, ttl_s=300)
        exceptions: list[str] = []

        def worker(base: int) -> None:
            for i in range(300):
                try:
                    lru.set(f"k{base}-{i}", i)
                    lru.get(f"k{base}-{i}")
                except Exception as e:  # pragma: no cover - only on regression
                    exceptions.append(f"{type(e).__name__}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(16)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert exceptions == [], f"concurrent access raised: {exceptions[:5]}"
        assert len(lru._data) <= lru.max_items
    finally:
        sys.setswitchinterval(original_interval)
