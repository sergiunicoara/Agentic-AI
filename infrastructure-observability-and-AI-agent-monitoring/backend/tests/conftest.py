"""Shared test rig.

The suite runs without Postgres or Redis: the service-layer calls each router
makes are stubbed, so what gets exercised is the wiring that actually enforces
policy - dependencies, ABAC filtering, and the gRPC servicer.
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.api import fastapi_app  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import get_db  # noqa: E402

TEST_JWT_SECRET = "test-secret-that-is-at-least-32-characters-long"


class FakeSession:
    """Async-session stand-in. execute() must be wired up by the test that needs it."""

    def __init__(self):
        self.added = []
        self.deleted = []
        self.committed = 0
        self.execute_results = []

    async def execute(self, *_args, **_kwargs):
        if not self.execute_results:
            raise AssertionError("unexpected database access")
        return self.execute_results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass

    async def refresh(self, obj=None, *_args, **_kwargs):
        # Stand in for the column defaults a real flush would have applied.
        table = getattr(type(obj), "__table__", None)
        if table is None:
            return
        for col in table.columns:
            default = col.default
            if getattr(obj, col.name, None) is None and default is not None and default.is_scalar:
                setattr(obj, col.name, default.arg)


class FakeAuditSession:
    """Swallows the audit-log write so tests do not need Postgres."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def add(self, _obj):
        pass

    async def commit(self):
        pass


@pytest.fixture(autouse=True)
def _isolate_backends(monkeypatch):
    """Pin the signing secret and keep every request off Redis and Postgres."""
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")

    async def _not_revoked(_jti):
        return False

    async def _active(_user_id):
        return True

    import app.grpc_server as grpc_server
    import app.middleware.audit_log as audit_log
    import app.services.auth_service as auth_service

    monkeypatch.setattr(auth_service, "is_revoked", _not_revoked)
    monkeypatch.setattr(auth_service, "is_user_active", _active)
    monkeypatch.setattr(grpc_server, "is_revoked", _not_revoked)
    monkeypatch.setattr(grpc_server, "is_user_active", _active)
    monkeypatch.setattr(audit_log, "AsyncSessionLocal", FakeAuditSession)


@pytest.fixture
def db() -> FakeSession:
    session = FakeSession()

    async def _override():
        yield session

    fastapi_app.dependency_overrides[get_db] = _override
    yield session
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(db) -> TestClient:
    with TestClient(fastapi_app) as c:
        yield c


def make_token(
    *,
    sub: str = "user-1",
    email: str = "user@example.com",
    role: str = "viewer",
    department: str = "",
    clearance_level: int = 0,
    expires_in_minutes: int = 60,
    jti: str = "",
) -> str:
    payload = {
        "sub": sub,
        "email": email,
        "role": role,
        "department": department,
        "clearance_level": clearance_level,
        "jti": jti or str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_span(
    *,
    span_id: str = "span-1",
    trace_id: str = "trace-1",
    sensitivity: str = "internal",
    owner_email: str = "",
    event_type: str = "llm_call",
):
    attributes = {"data_sensitivity": sensitivity}
    if owner_email:
        attributes["owner_email"] = owner_email
    return SimpleNamespace(
        id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        event_type=event_type,
        timestamp_ms=1_700_000_000_000,
        duration_ms=42,
        input_tokens=10,
        output_tokens=5,
        model="claude-sonnet-4-6",
        status="ok",
        error_message=None,
        attributes=attributes,
    )


def make_trace(trace_id: str = "trace-1", agent_name: str = "researcher", spans=None):
    return SimpleNamespace(
        id=trace_id,
        agent_name=agent_name,
        task_id="task-1",
        outcome="success",
        created_at=datetime(2026, 9, 4, 12, 0, 0),
        spans=spans if spans is not None else [],
    )
