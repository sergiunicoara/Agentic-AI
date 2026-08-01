"""Small, optional observability setup shared by API, ingestion, and MCP paths."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from app.config import get_settings

_configured = False


def configure_tracing() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    for name, value in {
        "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
        "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key,
        "LANGFUSE_BASE_URL": settings.langfuse_base_url,
    }.items():
        if value:
            os.environ.setdefault(name, value)

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: get_settings().otel_service_name})
    )
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True


def tracer():
    configure_tracing()
    return trace.get_tracer("codex")


@contextmanager
def span(name: str, **attributes: object) -> Iterator[object]:
    with tracer().start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, str(value))
        yield current
