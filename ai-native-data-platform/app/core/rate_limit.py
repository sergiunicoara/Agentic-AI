from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Dict

from app.core.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


@dataclass
class TokenBucket:
    rate: float
    capacity: int
    tokens: float
    last_refill: float

    def allow(self, cost: float = 1.0) -> bool:
        now = time.time()
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class WorkspaceRateLimiter:
    """Per-workspace token bucket.

    This protects the system under load and provides a backpressure signal
    (HTTP 429) rather than letting tail latencies explode.

    For distributed enforcement, this can be replaced by a Redis/Lua
    implementation, but an in-process limiter is often a good first guard.
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        redis_url = getattr(settings, "redis_url", "")
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True) if redis_url and redis else None

    _LUA = """
    local now = tonumber(ARGV[1])
    local rate = tonumber(ARGV[2])
    local capacity = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])
    local values = redis.call('HMGET', KEYS[1], 'tokens', 'updated_at')
    local tokens = tonumber(values[1]) or capacity
    local updated = tonumber(values[2]) or now
    tokens = math.min(capacity, tokens + math.max(0, now - updated) * rate)
    local allowed = 0
    if tokens >= cost then tokens = tokens - cost; allowed = 1 end
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_at', now)
    redis.call('EXPIRE', KEYS[1], math.max(60, math.ceil((capacity / math.max(rate, 0.001)) * 2)))
    return allowed
    """

    def allow(self, workspace_id: str) -> bool:
        if self._redis is not None:
            try:
                allowed = self._redis.eval(
                    self._LUA,
                    1,
                    f"rate_limit:{workspace_id}",
                    time.time(),
                    settings.per_workspace_rps,
                    settings.per_workspace_burst,
                    1.0,
                )
                return bool(int(allowed))
            except Exception:
                pass

        with self._lock:
            bucket = self._buckets.get(workspace_id)
            if bucket is None:
                bucket = TokenBucket(
                    rate=settings.per_workspace_rps,
                    capacity=settings.per_workspace_burst,
                    tokens=float(settings.per_workspace_burst),
                    last_refill=time.time(),
                )
                self._buckets[workspace_id] = bucket
            return bucket.allow(1.0)


rate_limiter = WorkspaceRateLimiter()
