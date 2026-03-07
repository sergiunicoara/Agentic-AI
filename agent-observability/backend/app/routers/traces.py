from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.auth_service import get_current_user
from app.services.trace_service import get_trace_with_spans, get_traces

router = APIRouter(prefix="/traces", tags=["traces"])


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


@router.get("", response_model=list[TraceOut])
async def list_traces(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    traces = await get_traces(db, agent_name=agent_name, limit=limit, offset=offset)
    return [
        TraceOut(
            id=t.id,
            agent_name=t.agent_name,
            task_id=t.task_id,
            outcome=t.outcome,
            created_at=t.created_at.isoformat(),
        )
        for t in traces
    ]


@router.get("/{trace_id}", response_model=TraceDetailOut)
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    trace = await get_trace_with_spans(trace_id, db)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return TraceDetailOut(
        id=trace.id,
        agent_name=trace.agent_name,
        task_id=trace.task_id,
        outcome=trace.outcome,
        created_at=trace.created_at.isoformat(),
        spans=[SpanOut.model_validate(s) for s in trace.spans],
    )
