"""Optional OpenTelemetry bridge.

When OTel is set up in the host process, AgentTracer will also create
native OTel spans alongside the gRPC events so that traces appear in
any OTel-compatible backend (Jaeger, Honeycomb, Grafana Tempo, etc.).
"""

from contextlib import contextmanager
from typing import Any, Generator, Optional


def _try_get_tracer(service_name: str):
    try:
        from opentelemetry import trace

        return trace.get_tracer(service_name)
    except ImportError:
        return None


class OtelBridge:
    def __init__(self, service_name: str = "agent-sdk"):
        self._tracer = _try_get_tracer(service_name)

    @contextmanager
    def span(self, name: str, attributes: Optional[dict] = None) -> Generator[Any, None, None]:
        if self._tracer is None:
            yield None
            return

        with self._tracer.start_as_current_span(name) as otel_span:
            if attributes:
                for k, v in attributes.items():
                    otel_span.set_attribute(k, str(v))
            yield otel_span
