# app/telemetry/tracing.py
import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
except Exception:  # pragma: no cover - OTLP exporter might not be installed
    OTLPSpanExporter = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def configure_tracer(
    service_name: str, otlp_endpoint: Optional[str] = None
) -> None:
    """
    Configure OpenTelemetry tracing.
    If OTEL_EXPORTER_OTLP_ENDPOINT is set, we send spans there.
    Otherwise we log spans to console (or just keep a no-op provider).
    """
    # Only configure once
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        # Already configured
        return

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint and OTLPSpanExporter is not None:
        logger.info(
            "Initializing OTLP trace exporter to %s", otlp_endpoint
        )
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    else:
        logger.info(
            "Tracer initialized without remote exporter (no OTEL_EXPORTER_OTLP_ENDPOINT)."
        )
        exporter = ConsoleSpanExporter()

    span_processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(span_processor)

    trace.set_tracer_provider(provider)
