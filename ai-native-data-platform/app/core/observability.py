from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from typing import Any

try:
    import structlog  # type: ignore
except Exception:  # pragma: no cover
    structlog = None
from prometheus_client import Counter, Histogram
from sqlalchemy import text

from app.core.config import settings
from app.data.db import write_session_scope

import logging
log = structlog.get_logger() if structlog is not None else logging.getLogger("ai_platform")


# --- Metrics
HTTP_REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["route", "method", "status"])
HTTP_LATENCY = Histogram("http_request_latency_seconds", "HTTP request latency seconds", ["route", "method"])

INGEST_JOBS = Counter("ingest_jobs_total", "Ingest jobs processed", ["status"])
INGEST_LATENCY = Histogram("ingest_latency_seconds", "Ingest latency seconds")

RETRIEVAL_LATENCY = Histogram("retrieval_latency_seconds", "Retrieval latency seconds")
GEN_LATENCY = Histogram("generation_latency_seconds", "Generation latency seconds")
GEN_FAILURES = Counter("generation_failures_total", "Generation failures", ["code"])

RELIABILITY_VIOLATIONS = Counter(
    "reliability_violations_total",
    "Reliability contract violations",
    ["type"],
)


@contextmanager
def timer(hist: Histogram, labels: dict | None = None):
    t0 = time.time()
    try:
        yield
    finally:
        dt = time.time() - t0
        if labels:
            hist.labels(**labels).observe(dt)
        else:
            hist.observe(dt)


def emit_event(name: str, payload: dict[str, Any]) -> None:
    """Structured event emission.

    Events are logged via structlog and may optionally be persisted to Postgres.
    """
    log.info("event", name=name, **payload)


def persist_trace(*, trace_type: str, workspace_id: str, body: dict[str, Any], latency_ms: int) -> None:
    """Persist a trace to Postgres.

    This is intentionally best-effort; it must never fail the online path.
    """
    if trace_type == "retrieval" and not settings.log_retrieval:
        return
    if trace_type == "generation" and not settings.log_generation:
        return

    try:
        with write_session_scope() as db:
            db.execute(
                text(
                    """
                    INSERT INTO trace_log (id, trace_type, workspace_id, body, latency_ms)
                    VALUES (:id, :t, :w, :b::jsonb, :ms)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "t": trace_type,
                    "w": workspace_id,
                    "b": json.dumps(body),
                    "ms": int(latency_ms),
                },
            )
    except Exception:
        return
