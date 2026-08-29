"""
Layer 5: OpenTelemetry Tracer Setup

Configures the OTel SDK and provides a get_tracer() factory used by every layer.

Span hierarchy emitted per review session:
  orchestrator.run
    ├── orchestrator.mcp_tools
    │     ├── mcp.linter
    │     ├── mcp.type_checker
    │     └── mcp.security_scanner
    ├── orchestrator.subagents
    │     ├── subagent.security
    │     ├── subagent.architecture
    │     └── subagent.style
    └── review_agent.review

Exporter priority:
  1. OTLP gRPC → OTEL_EXPORTER_ENDPOINT (e.g. Agent Observability Dashboard at localhost:4317)
  2. Console (stdout) if OTLP endpoint is not configured

This integrates with the agent-observability project in this workspace.
"""
import os
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_SERVICE_NAME = "ai-engineering-workflow-toolkit"
_initialized = False


def _setup_tracer_provider() -> None:
    global _initialized
    if _initialized:
        return

    resource = Resource.create({"service.name": _SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_ENDPOINT", "")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            pass  # OTLP package not available — spans are collected but not exported
    elif os.getenv("AIWT_DEBUG", "").lower() in ("1", "true"):
        # Only emit spans to console when explicitly requested
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _initialized = True


@lru_cache(maxsize=None)
def get_tracer(name: str):
    """Return a named OTel tracer. Initialises the provider on first call."""
    _setup_tracer_provider()
    return trace.get_tracer(f"{_SERVICE_NAME}.{name}")
