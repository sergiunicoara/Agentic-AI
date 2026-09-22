"""
OpenTelemetry tracing + structured logging for the A2A layer.

Tracing is configured only when OTEL_EXPORTER_OTLP_ENDPOINT is set; with
no endpoint configured, `trace.get_tracer` returns the SDK's default
no-op tracer, so span calls are inert (no overhead, no crash) in local
dev and tests.
"""
import logging
import os

from opentelemetry import trace

logger = logging.getLogger("sentinel.a2a")

_configured = False


def configure_tracing() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "sentinel-a2a"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)


tracer = trace.get_tracer("sentinel.a2a")
