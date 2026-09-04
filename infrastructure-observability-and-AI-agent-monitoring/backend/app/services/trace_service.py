"""Persists incoming AgentEvents to Postgres and broadcasts them on the event bus."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models.trace import AgentTrace, Span
from app.services.event_bus import event_bus


def build_trace_upsert(event):
    """INSERT ... ON CONFLICT for the parent trace row.

    Split out from persist_event so the conflict clause can be asserted without
    a live database.
    """
    stmt = pg_insert(AgentTrace).values(
        id=event.trace_id,
        agent_name=event.agent_name,
        task_id=event.task_id or None,
        outcome=event.outcome or "pending",
    )
    return stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "agent_name": stmt.excluded.agent_name,
            # proto3 strings default to "", so an event carrying no outcome (a
            # plain span, or a retried/late span_start) must leave a finished
            # trace outcome alone instead of blanking it back to empty.
            "outcome": func.coalesce(
                func.nullif(stmt.excluded.outcome, ""),
                AgentTrace.__table__.c.outcome,
            ),
        },
    )


def build_span_upsert(event):
    """INSERT ... ON CONFLICT for the span row.

    span_start creates the row; the closing event updates it with the real
    duration/token values (on_conflict_do_nothing would discard them).
    """
    span_id = event.span_id or str(uuid.uuid4())
    stmt = pg_insert(Span).values(
        id=span_id,
        trace_id=event.trace_id,
        parent_span_id=event.parent_span_id or None,
        event_type=event.event_type,
        timestamp_ms=event.timestamp_ms,
        duration_ms=event.duration_ms,
        input_tokens=event.input_tokens,
        output_tokens=event.output_tokens,
        model=event.model or None,
        status=event.status or "ok",
        error_message=event.error_message or None,
        attributes=dict(event.attributes),
    )
    return stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "event_type": stmt.excluded.event_type,
            "duration_ms": stmt.excluded.duration_ms,
            "input_tokens": stmt.excluded.input_tokens,
            "output_tokens": stmt.excluded.output_tokens,
            "status": stmt.excluded.status,
            "error_message": stmt.excluded.error_message,
            "attributes": stmt.excluded.attributes,
        },
    )


async def persist_event(event) -> None:
    """Upsert trace + span rows from a gRPC AgentEvent message."""
    async with AsyncSessionLocal() as db:
        await db.execute(build_trace_upsert(event))
        await db.execute(build_span_upsert(event))
        await db.commit()


async def get_traces(
    db: AsyncSession,
    agent_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentTrace]:
    q = (
        select(AgentTrace)
        .options(selectinload(AgentTrace.spans))
        .order_by(AgentTrace.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if agent_name:
        q = q.where(AgentTrace.agent_name == agent_name)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_trace_with_spans(trace_id: str, db: AsyncSession) -> Optional[AgentTrace]:
    result = await db.execute(
        select(AgentTrace).where(AgentTrace.id == trace_id)
    )
    trace = result.scalar_one_or_none()
    if trace:
        await db.refresh(trace, ["spans"])
    return trace


async def handle_event(event) -> None:
    """Persist to DB and broadcast to live subscribers."""
    await persist_event(event)
    await event_bus.publish(event)
