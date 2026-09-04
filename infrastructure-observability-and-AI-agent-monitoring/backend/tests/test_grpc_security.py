"""gRPC transport coverage.

The live stream is a second read path over the same data as the REST API, and
the emit path is the only write path. Both had defects that endpoint tests on
the REST side could never have caught.
"""

import asyncio

import grpc
import pytest

import app.grpc_server as grpc_server
from app.config import settings
from app.generated import agent_events_pb2
from app.grpc_server import AgentEventServicer, _abac_allows
from conftest import make_token


class Aborted(Exception):
    def __init__(self, code, details):
        super().__init__(details)
        self.code = code
        self.details = details


class FakeContext:
    """Records aborts. abort() raises, exactly as grpc.aio does."""

    def __init__(self, metadata=None):
        self._metadata = metadata or {}
        self.aborts = []

    def invocation_metadata(self):
        return tuple(self._metadata.items())

    async def abort(self, code, details):
        self.aborts.append((code, details))
        raise Aborted(code, details)

    def cancelled(self):
        return False


def an_event(**overrides):
    fields = dict(
        trace_id="trace-1",
        span_id="span-1",
        agent_name="researcher",
        event_type="llm_call",
        timestamp_ms=1_700_000_000_000,
    )
    fields.update(overrides)
    return agent_events_pb2.AgentEvent(**fields)


# --- ingestion auth ---------------------------------------------------------

def test_emit_rejects_a_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "emit_agent_keys", '{"researcher":"right-key"}')
    ctx = FakeContext({"x-api-key": "wrong-key"})

    with pytest.raises(Aborted):
        asyncio.run(AgentEventServicer().EmitEvent(an_event(), ctx))
    assert ctx.aborts[0][0] == grpc.StatusCode.UNAUTHENTICATED


def test_emit_rejects_a_key_scoped_to_another_agent(monkeypatch):
    monkeypatch.setattr(settings, "emit_agent_keys", '{"researcher":"right-key"}')
    ctx = FakeContext({"x-api-key": "right-key"})

    with pytest.raises(Aborted):
        asyncio.run(AgentEventServicer().EmitEvent(an_event(agent_name="writer"), ctx))
    assert ctx.aborts[0][0] == grpc.StatusCode.UNAUTHENTICATED


def test_emit_accepts_a_correctly_scoped_key(monkeypatch):
    monkeypatch.setattr(settings, "emit_agent_keys", '{"researcher":"right-key"}')
    handled = []

    async def handle_event(event):
        handled.append(event)

    monkeypatch.setattr(grpc_server, "handle_event", handle_event)
    ctx = FakeContext({"x-api-key": "right-key"})

    response = asyncio.run(AgentEventServicer().EmitEvent(an_event(), ctx))
    assert response.accepted is True
    assert len(handled) == 1


def test_emit_does_not_leak_internal_errors(monkeypatch):
    """A persistence failure must not hand driver/SQL detail to ingest clients."""
    monkeypatch.setattr(settings, "emit_agent_keys", '{"researcher":"right-key"}')

    async def boom(_event):
        raise RuntimeError("relation \"spans\" does not exist at 10.0.0.7:5432")

    monkeypatch.setattr(grpc_server, "handle_event", boom)
    ctx = FakeContext({"x-api-key": "right-key"})

    with pytest.raises(Aborted):
        asyncio.run(AgentEventServicer().EmitEvent(an_event(), ctx))

    (code, details), = ctx.aborts
    assert code == grpc.StatusCode.INTERNAL
    assert details == "Failed to persist event"
    assert "spans" not in details and "5432" not in details


def test_emit_rejects_oversized_attribute_payloads(monkeypatch):
    monkeypatch.setattr(settings, "emit_agent_keys", '{"researcher":"right-key"}')
    ctx = FakeContext({"x-api-key": "right-key"})
    event = an_event(attributes={f"k{i}": "v" for i in range(65)})

    with pytest.raises(Aborted):
        asyncio.run(AgentEventServicer().EmitEvent(event, ctx))
    assert ctx.aborts[0][0] == grpc.StatusCode.INVALID_ARGUMENT


# --- live stream auth -------------------------------------------------------

def _subscribe(token, ctx):
    request = agent_events_pb2.SubscribeRequest(session_token=token)
    stream = AgentEventServicer().SubscribeEvents(request, ctx)
    return asyncio.run(stream.__anext__())


def test_subscribe_rejects_an_invalid_token():
    ctx = FakeContext()
    with pytest.raises(Aborted):
        _subscribe("not-a-jwt", ctx)
    assert ctx.aborts == [(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")]


def test_subscribe_reports_revocation_and_aborts_only_once(monkeypatch):
    """abort() raises; if it sits inside a broad try/except the real reason is
    swallowed and the context is aborted a second time."""

    async def revoked(_jti):
        return True

    monkeypatch.setattr(grpc_server, "is_revoked", revoked)
    ctx = FakeContext()

    with pytest.raises(Aborted):
        _subscribe(make_token(), ctx)
    assert ctx.aborts == [(grpc.StatusCode.UNAUTHENTICATED, "Token revoked")]


def test_subscribe_reports_a_deactivated_account(monkeypatch):
    async def inactive(_user_id):
        return False

    monkeypatch.setattr(grpc_server, "is_user_active", inactive)
    ctx = FakeContext()

    with pytest.raises(Aborted):
        _subscribe(make_token(), ctx)
    assert ctx.aborts == [(grpc.StatusCode.UNAUTHENTICATED, "Account inactive")]


def test_subscribe_fails_closed_when_revocation_lookup_is_down(monkeypatch):
    async def unavailable(_jti):
        raise ConnectionError("redis down")

    monkeypatch.setattr(grpc_server, "is_revoked", unavailable)
    ctx = FakeContext()

    with pytest.raises(Aborted):
        _subscribe(make_token(), ctx)
    assert ctx.aborts[0][0] == grpc.StatusCode.UNAVAILABLE


# --- stream-side ABAC -------------------------------------------------------

def test_stream_applies_the_same_span_policy_as_rest():
    viewer = {"role": "viewer", "email": "v@example.com", "clearance_level": 0}
    confidential = an_event(attributes={"data_sensitivity": "confidential"})
    public = an_event(attributes={"data_sensitivity": "public"})

    assert _abac_allows(viewer, public) is True
    assert _abac_allows(viewer, confidential) is False


def test_stream_lets_an_owner_see_their_own_confidential_span():
    viewer = {"role": "viewer", "email": "owner@example.com", "clearance_level": 0}
    event = an_event(
        attributes={"data_sensitivity": "confidential", "owner_email": "owner@example.com"}
    )
    assert _abac_allows(viewer, event) is True
