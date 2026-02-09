from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Deque, Tuple

from prometheus_client import Gauge


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

    def observe(self, latency_ms: float, *, is_error: bool, is_unknown: bool) -> None:
        self._events.append((0.0, float(latency_ms), 1 if is_error else 0, 1 if is_unknown else 0))
        self._publish()

    def _publish(self) -> None:
        if not self._events:
            return
        lats = [e[1] for e in self._events]
        errs = sum(e[2] for e in self._events)
        unks = sum(e[3] for e in self._events)
        n = len(self._events)
        self._last_p95 = _p95(lats)
        self._last_err_rate = errs / n
        self._last_unknown_rate = unks / n
        SLO_ROLLING_P95_LATENCY_MS.set(self._last_p95)
        SLO_ROLLING_ERROR_RATE.set(self._last_err_rate)
        SLO_ROLLING_UNKNOWN_RATE.set(self._last_unknown_rate)

    def snapshot(self) -> dict[str, float]:
        return {
            "p95_latency_ms": float(self._last_p95),
            "error_rate": float(self._last_err_rate),
            "unknown_rate": float(self._last_unknown_rate),
        }


rolling_slo = RollingWindowSLO()
