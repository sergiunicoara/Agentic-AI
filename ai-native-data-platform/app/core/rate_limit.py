from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

from app.core.config import settings


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

    def allow(self, workspace_id: str) -> bool:
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
