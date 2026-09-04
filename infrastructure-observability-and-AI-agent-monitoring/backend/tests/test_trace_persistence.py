"""The trace upsert must not regress a finished trace back to an empty outcome."""

from sqlalchemy.dialects import postgresql

from app.generated import agent_events_pb2
from app.services.trace_service import build_trace_upsert

_PG = postgresql.dialect()


def _compiled(event) -> str:
    return str(build_trace_upsert(event).compile(dialect=_PG))


def test_outcome_is_preserved_when_the_event_carries_none():
    event = agent_events_pb2.AgentEvent(
        trace_id="trace-1", span_id="span-1", agent_name="researcher"
    )
    sql = _compiled(event).lower()

    # coalesce(nullif(excluded.outcome, ''), agent_traces.outcome)
    assert "coalesce" in sql
    assert "nullif" in sql
    assert "agent_traces.outcome" in sql


def test_a_new_trace_defaults_to_pending():
    event = agent_events_pb2.AgentEvent(
        trace_id="trace-1", span_id="span-1", agent_name="researcher"
    )
    params = build_trace_upsert(event).compile(dialect=_PG).params
    assert params["outcome"] == "pending"


def test_an_event_with_an_outcome_still_sets_it():
    event = agent_events_pb2.AgentEvent(
        trace_id="trace-1", span_id="span-1", agent_name="researcher", outcome="success"
    )
    params = build_trace_upsert(event).compile(dialect=_PG).params
    assert params["outcome"] == "success"
