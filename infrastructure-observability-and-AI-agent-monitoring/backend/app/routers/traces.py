from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.abac import check_span_access
from app.services.auth_service import verified_payload
from app.services.trace_service import get_trace_with_spans, get_traces

router = APIRouter(prefix="/traces", tags=["traces"])

# Bounds the forward scan in list_traces when most rows are unreadable.
_MAX_SCAN_PAGES = 10


class SpanOut(BaseModel):
    id: str
    trace_id: str
    parent_span_id: Optional[str]
    event_type: str
    timestamp_ms: int
    duration_ms: int
    input_tokens: int
    output_tokens: int
    model: Optional[str]
    status: str
    error_message: Optional[str]
    attributes: dict

    class Config:
        from_attributes = True


class TraceOut(BaseModel):
    id: str
    agent_name: str
    task_id: Optional[str]
    outcome: str
    created_at: str

    class Config:
        from_attributes = True


class TraceDetailOut(TraceOut):
    spans: list[SpanOut] = []


def _span_resource(span, agent_name: str = "") -> dict:
    attrs = span.attributes if isinstance(span.attributes, dict) else {}
    return {
        "data_sensitivity": attrs.get("data_sensitivity", "internal"),
        "owner_email": attrs.get("owner_email", ""),
        "agent_name": agent_name,
    }


def _trace_is_readable(subject: dict, trace) -> bool:
    """A trace is listable when it has at least one readable span.

    Traces with no spans at all carry no protected content, so their metadata
    stays visible (see README — trace metadata is public, span bodies are not).
    """
    if not trace.spans:
        return True
    return any(
        check_span_access(subject, _span_resource(span, trace.agent_name), "read")
        for span in trace.spans
    )


@router.get("", response_model=list[TraceOut])
async def list_traces(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    subject: dict = Depends(verified_payload),
):
    # ABAC is evaluated in Python (one policy, shared with the gRPC stream), so
    # it cannot be pushed into the LIMIT. Scan forward until a full page of
    # readable traces is collected, so a page is not silently short just because
    # the caller lacks clearance for some rows. `offset` indexes source rows.
    visible: list[TraceOut] = []
    scan_offset = offset
    for _ in range(_MAX_SCAN_PAGES):
        traces = await get_traces(db, agent_name=agent_name, limit=limit, offset=scan_offset)
        if not traces:
            break
        scan_offset += len(traces)

        for t in traces:
            if _trace_is_readable(subject, t):
                visible.append(
                    TraceOut(
                        id=t.id,
                        agent_name=t.agent_name,
                        task_id=t.task_id,
                        outcome=t.outcome,
                        created_at=t.created_at.isoformat(),
                    )
                )
                if len(visible) >= limit:
                    return visible

        if len(traces) < limit:      # source exhausted
            break
    return visible


@router.get("/{trace_id}", response_model=TraceDetailOut)
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    subject: dict = Depends(verified_payload),
):
    trace = await get_trace_with_spans(trace_id, db)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # ABAC: filter spans by subject's clearance + ownership
    permitted_spans = [
        SpanOut.model_validate(s)
        for s in trace.spans
        if check_span_access(subject, _span_resource(s, trace.agent_name), "read")
    ]

    if not permitted_spans and trace.spans:
        raise HTTPException(status_code=403, detail="Insufficient clearance for this trace")

    return TraceDetailOut(
        id=trace.id,
        agent_name=trace.agent_name,
        task_id=trace.task_id,
        outcome=trace.outcome,
        created_at=trace.created_at.isoformat(),
        spans=permitted_spans,
    )
