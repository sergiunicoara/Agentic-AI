"""Persists incoming AgentEvents to Postgres and broadcasts them on the event bus."""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.trace import AgentTrace, Span
from app.services.event_bus import event_bus


async def persist_event(event) -> None:
    """Upsert trace + span rows from a gRPC AgentEvent message."""
    async with AsyncSessionLocal() as db:
        # Upsert the parent trace
        await db.execute(
            pg_insert(AgentTrace)
            .values(
                id=event.trace_id,
                agent_name=event.agent_name,
                task_id=event.task_id or None,
                outcome=event.outcome or "pending",
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"outcome": event.outcome, "agent_name": event.agent_name},
            )
        )

        # Upsert span: span_start creates the row; span_end updates it with real
        # duration/token values (on_conflict_do_nothing would discard span_end data).
        span_id = event.span_id or str(uuid.uuid4())
        await db.execute(
            pg_insert(Span)
            .values(
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
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "event_type": event.event_type,
                    "duration_ms": event.duration_ms,
                    "input_tokens": event.input_tokens,
                    "output_tokens": event.output_tokens,
                    "status": event.status or "ok",
                    "error_message": event.error_message or None,
                    "attributes": dict(event.attributes),
                },
            )
        )

        await db.commit()


async def get_traces(
    db: AsyncSession,
    agent_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentTrace]:
    q = select(AgentTrace).order_by(AgentTrace.created_at.desc()).limit(limit).offset(offset)
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
