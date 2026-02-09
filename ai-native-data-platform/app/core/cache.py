from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Any, Optional

from app.core.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


class InMemoryLRU:
    def __init__(self, max_items: int, ttl_s: int):
        self.max_items = max_items
        self.ttl_s = ttl_s
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        expires_at = time.time() + self.ttl_s
        self._data[key] = (expires_at, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)


class Cache:
    """Best-effort caching layer.

    - If REDIS_URL is configured and `redis` is installed, uses Redis for a
      distributed cache (useful for multiple API replicas).
    - Otherwise falls back to an in-process LRU with TTL.

    The cache is deliberately simple and safe: failures are treated as cache
    misses and do not affect correctness.
    """

    def __init__(self) -> None:
        self._mem = InMemoryLRU(settings.cache_max_items, settings.cache_ttl_s)
        self._redis = None
        if settings.redis_url and redis is not None:
            try:
                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                # ping to validate
                self._redis.ping()
            except Exception:
                self._redis = None

    def get_json(self, key: str) -> Optional[Any]:
        try:
            if self._redis is not None:
                raw = self._redis.get(key)
                if raw is None:
                    return None
                return json.loads(raw)
        except Exception:
            return None

        return self._mem.get(key)

    def set_json(self, key: str, value: Any, ttl_s: Optional[int] = None) -> None:
        try:
            if self._redis is not None:
                self._redis.setex(key, ttl_s or settings.cache_ttl_s, json.dumps(value))
                return
        except Exception:
            pass

        self._mem.set(key, value)


cache = Cache()
