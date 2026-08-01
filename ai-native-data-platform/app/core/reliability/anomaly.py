from __future__ import annotations

"""Lightweight anomaly detection for operational metrics.

Production platforms typically rely on telemetry systems for anomaly detection
(Prometheus, stream processing, etc.). This module provides a tiny in-process
detector suitable for a portfolio repo.

Approach:
  - EWMA baseline
  - z-score of recent value vs EWMA volatility proxy

Signals are exported as Prometheus gauges and can also be logged via trace_log.
"""

from dataclasses import dataclass

from prometheus_client import Gauge
from app.core.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


ANOMALY_SCORE = Gauge(
    "platform_anomaly_score",
    "Anomaly score for key SLO indicators (higher means more anomalous)",
    ["signal"],
)


@dataclass
class EWMAAnomalyDetector:
    alpha: float = 0.2
    min_var: float = 1e-6
    state_key: str = "slo:anomaly:default"

    def __post_init__(self) -> None:
        self.mean = 0.0
        self.var = 0.0
        self.initialized = False
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url and redis else None

    _LUA = """
    local x = tonumber(ARGV[1])
    local alpha = tonumber(ARGV[2])
    local min_var = tonumber(ARGV[3])
    local initialized = redis.call('HGET', KEYS[1], 'initialized')
    if initialized ~= '1' then
      redis.call('HMSET', KEYS[1], 'initialized', '1', 'mean', x, 'var', 0)
      redis.call('EXPIRE', KEYS[1], 86400)
      return 0
    end
    local mean = tonumber(redis.call('HGET', KEYS[1], 'mean')) or 0
    local var = tonumber(redis.call('HGET', KEYS[1], 'var')) or 0
    local previous_mean = mean
    mean = alpha * x + (1 - alpha) * mean
    local resid = x - previous_mean
    var = alpha * resid * resid + (1 - alpha) * var
    redis.call('HMSET', KEYS[1], 'mean', mean, 'var', var)
    redis.call('EXPIRE', KEYS[1], 86400)
    return math.abs(x - mean) / math.sqrt(math.max(var, min_var))
    """

    def update(self, x: float) -> float:
        x = float(x)
        if self._redis is not None:
            try:
                return float(self._redis.eval(self._LUA, 1, self.state_key, x, self.alpha, self.min_var))
            except Exception:
                pass
        if not self.initialized:
            self.mean = x
            self.var = 0.0
            self.initialized = True
            return 0.0

        # EWMA mean
        prev_mean = self.mean
        self.mean = (self.alpha * x) + ((1.0 - self.alpha) * self.mean)

        # EWMA variance (volatility proxy)
        resid = x - prev_mean
        self.var = (self.alpha * (resid * resid)) + ((1.0 - self.alpha) * self.var)
        std = max(self.var, self.min_var) ** 0.5
        z = abs(x - self.mean) / std
        return float(z)


latency_detector = EWMAAnomalyDetector(alpha=0.15, state_key="slo:anomaly:latency")
error_detector = EWMAAnomalyDetector(alpha=0.20, state_key="slo:anomaly:error")
unknown_detector = EWMAAnomalyDetector(alpha=0.20, state_key="slo:anomaly:unknown")


def observe_slo_signals(p95_latency_ms: float, error_rate: float, unknown_rate: float) -> dict[str, float]:
    """Update detectors and export scores."""
    s1 = latency_detector.update(p95_latency_ms)
    s2 = error_detector.update(error_rate)
    s3 = unknown_detector.update(unknown_rate)
    ANOMALY_SCORE.labels(signal="p95_latency_ms").set(s1)
    ANOMALY_SCORE.labels(signal="error_rate").set(s2)
    ANOMALY_SCORE.labels(signal="unknown_rate").set(s3)
    return {"p95_latency_ms": s1, "error_rate": s2, "unknown_rate": s3}
