# app/otel.py

from __future__ import annotations
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

# Create provider
_tracer_provider = TracerProvider()
_exporter = ConsoleSpanExporter()
_tracer_provider.add_span_processor(SimpleSpanProcessor(_exporter))

trace.set_tracer_provider(_tracer_provider)


def get_tracer(name: str):
    return trace.get_tracer(name)
