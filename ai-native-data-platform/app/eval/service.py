from __future__ import annotations

from typing import Any

from app.core.observability import persist_trace
from app.schemas import RetrievedChunk


def compute_online_signals(*, workspace_id: str, query: str, retrieved: list[RetrievedChunk], unknown: bool, latency_ms: int) -> None:
    """Persist lightweight online signals for later offline analysis.

    In a production platform this would feed monitoring (SLOs), drift detection,
    and active evaluation sampling.
    """
    persist_trace(
        trace_type="online_signal",
        workspace_id=workspace_id,
        body={
            "query": query,
            "unknown": bool(unknown),
            "latency_ms": int(latency_ms),
            "retrieved_count": len(retrieved),
            "retrieved_docs": list({c.document_id for c in retrieved}),
            "top_score": float(retrieved[0].score) if retrieved else 0.0,
        },
        latency_ms=int(latency_ms),
    )
