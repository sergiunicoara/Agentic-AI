from __future__ import annotations

import collections
import json
import time
import uuid
from dataclasses import dataclass
from typing import Deque, Tuple

from prometheus_client import Gauge
from app.core.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


SLO_ROLLING_P95_LATENCY_MS = Gauge(
    "slo_rolling_p95_latency_ms",
    "Rolling p95 request latency (ms) over a bounded in-memory window",
)
SLO_ROLLING_ERROR_RATE = Gauge(
    "slo_rolling_error_rate",
    "Rolling error rate over a bounded in-memory window",
)
SLO_ROLLING_UNKNOWN_RATE = Gauge(
    "slo_rolling_unknown_rate",
    "Rolling unknown-response rate over a bounded in-memory window",
)


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs2 = sorted(xs)
    idx = int(round(0.95 * (len(xs2) - 1)))
    idx = max(0, min(len(xs2) - 1, idx))
    return float(xs2[idx])


@dataclass
class RollingWindowSLO:
    """In-process SLO aggregation.

    This is a lightweight stand-in for production telemetry pipelines
    (Prometheus queries, log-based metrics, or stream processing).

    It is useful in a portfolio repo because it makes the SLO concept explicit:
    online enforcement uses per-request ceilings, while SLOs are tracked as
    rolling aggregates for alerting.
    """

    max_events: int = 2000

    def __post_init__(self) -> None:
        self._events: Deque[Tuple[float, float, int, int]] = collections.deque(maxlen=self.max_events)
        # tuple: (ts, latency_ms, is_error, is_unknown)
        self._last_p95 = 0.0
        self._last_err_rate = 0.0
        self._last_unknown_rate = 0.0
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url and redis else None
        self._redis_key = "slo:rolling:events"

    def observe(self, latency_ms: float, *, is_error: bool, is_unknown: bool) -> None:
        if self._redis is not None:
            try:
                now = time.time()
                member = json.dumps(
                    {"latency_ms": float(latency_ms), "is_error": int(is_error), "is_unknown": int(is_unknown), "id": uuid.uuid4().hex},
                    separators=(",", ":"),
                )
                self._redis.zadd(self._redis_key, {member: now})
                count = int(self._redis.zcard(self._redis_key))
                if count > self.max_events:
                    self._redis.zremrangebyrank(self._redis_key, 0, count - self.max_events - 1)
                self._redis.expire(self._redis_key, 86_400)
                self._publish(self._redis_events())
                return
            except Exception:
                pass
        self._events.append((0.0, float(latency_ms), 1 if is_error else 0, 1 if is_unknown else 0))
        self._publish()

    def _redis_events(self) -> list[Tuple[float, float, int, int]]:
        if self._redis is None:
            return []
        out: list[Tuple[float, float, int, int]] = []
        for raw in self._redis.zrange(self._redis_key, 0, -1):
            try:
                item = json.loads(raw)
                out.append((0.0, float(item["latency_ms"]), int(item["is_error"]), int(item["is_unknown"])))
            except (TypeError, ValueError, KeyError):
                continue
        return out

    def _publish(self, events: list[Tuple[float, float, int, int]] | None = None) -> None:
        events = events if events is not None else list(self._events)
        if not events:
            return
        lats = [e[1] for e in events]
        errs = sum(e[2] for e in events)
        unks = sum(e[3] for e in events)
        n = len(events)
        self._last_p95 = _p95(lats)
        self._last_err_rate = errs / n
        self._last_unknown_rate = unks / n
        SLO_ROLLING_P95_LATENCY_MS.set(self._last_p95)
        SLO_ROLLING_ERROR_RATE.set(self._last_err_rate)
        SLO_ROLLING_UNKNOWN_RATE.set(self._last_unknown_rate)

    def snapshot(self) -> dict[str, float]:
        sample_count = len(self._events)
        if self._redis is not None:
            try:
                events = self._redis_events()
                self._publish(events)
                sample_count = len(events)
            except Exception:
                self._redis = None
        return {
            "p95_latency_ms": float(self._last_p95),
            "error_rate": float(self._last_err_rate),
            "unknown_rate": float(self._last_unknown_rate),
            "samples": float(sample_count),
        }


rolling_slo = RollingWindowSLO()
