from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict

from opentelemetry.metrics import get_meter


_meter = get_meter(__name__)

_request_counter = _meter.create_counter(
    name="agent_requests_total",
    unit="1",
    description="Total number of agent chat requests",
)

_latency_histogram = _meter.create_histogram(
    name="agent_request_latency_ms",
    unit="ms",
    description="Latency of agent chat requests",
)


@contextmanager
def track_request(path: str):
    """Context manager to record basic request metrics.

    Usage:
        with track_request("/chat"):
            ... handle request ...
    """
    start = time.time()
    try:
        yield
    finally:
        duration_ms = (time.time() - start) * 1000.0
        attributes: Dict[str, str] = {"path": path}
        try:
            _request_counter.add(1, attributes)
            _latency_histogram.record(duration_ms, attributes)
        except Exception:
            # Metrics must never break the main flow
            pass
