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


ANOMALY_SCORE = Gauge(
    "platform_anomaly_score",
    "Anomaly score for key SLO indicators (higher means more anomalous)",
    ["signal"],
)


@dataclass
class EWMAAnomalyDetector:
    alpha: float = 0.2
    min_var: float = 1e-6

    def __post_init__(self) -> None:
        self.mean = 0.0
        self.var = 0.0
        self.initialized = False

    def update(self, x: float) -> float:
        x = float(x)
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


latency_detector = EWMAAnomalyDetector(alpha=0.15)
error_detector = EWMAAnomalyDetector(alpha=0.20)
unknown_detector = EWMAAnomalyDetector(alpha=0.20)


def observe_slo_signals(p95_latency_ms: float, error_rate: float, unknown_rate: float) -> dict[str, float]:
    """Update detectors and export scores."""
    s1 = latency_detector.update(p95_latency_ms)
    s2 = error_detector.update(error_rate)
    s3 = unknown_detector.update(unknown_rate)
    ANOMALY_SCORE.labels(signal="p95_latency_ms").set(s1)
    ANOMALY_SCORE.labels(signal="error_rate").set(s2)
    ANOMALY_SCORE.labels(signal="unknown_rate").set(s3)
    return {"p95_latency_ms": s1, "error_rate": s2, "unknown_rate": s3}
