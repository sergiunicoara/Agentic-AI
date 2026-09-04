"""Endpoint-level authn/authz coverage.

Every one of these guards a property that was previously enforced only by
reading the code: see tasks/lessons.md for the two incidents where a policy
existed on one path and not another.
"""

import pytest

from app.services import auth_service
from conftest import auth, make_span, make_token, make_trace

TRACES = "/api/v1/traces"


# --- authentication ---------------------------------------------------------

def test_missing_bearer_is_rejected(client):
    assert client.get(TRACES).status_code == 401


def test_garbage_token_is_rejected(client):
    r = client.get(TRACES, headers=auth("not-a-jwt"))
    assert r.status_code == 401


def test_token_signed_with_another_secret_is_rejected(client):
    from jose import jwt

    forged = jwt.encode({"sub": "u", "role": "admin"}, "attacker-secret", algorithm="HS256")
    assert client.get(TRACES, headers=auth(forged)).status_code == 401


def test_expired_token_is_rejected(client):
    r = client.get(TRACES, headers=auth(make_token(expires_in_minutes=-1)))
    assert r.status_code == 401


def test_revoked_token_is_rejected(client, monkeypatch):
    async def revoked(_jti):
        return True

    monkeypatch.setattr(auth_service, "is_revoked", revoked)
    r = client.get(TRACES, headers=auth(make_token()))
    assert r.status_code == 401
    assert r.json()["detail"] == "Token revoked"


def test_deactivated_user_is_rejected(client, monkeypatch):
    async def inactive(_user_id):
        return False

    monkeypatch.setattr(auth_service, "is_user_active", inactive)
    r = client.get(TRACES, headers=auth(make_token()))
    assert r.status_code == 401
    assert r.json()["detail"] == "Account inactive"


# --- role policy ------------------------------------------------------------

def test_viewer_cannot_create_eval_run(client):
    r = client.post(
        "/api/v1/evals", json={"name": "run"}, headers=auth(make_token(role="viewer"))
    )
    assert r.status_code == 403


def test_developer_can_create_eval_run(client):
    r = client.post(
        "/api/v1/evals", json={"name": "run"}, headers=auth(make_token(role="developer"))
    )
    assert r.status_code == 201
    assert r.json()["created_by"] == "user-1"


def test_viewer_cannot_reach_admin_api(client):
    r = client.get("/api/v1/admin/users", headers=auth(make_token(role="viewer")))
    assert r.status_code == 403


def test_developer_cannot_reach_admin_api(client):
    r = client.get("/api/v1/admin/users", headers=auth(make_token(role="developer")))
    assert r.status_code == 403


def test_admin_cannot_remove_own_admin_role(client):
    r = client.patch(
        "/api/v1/admin/users/admin-1",
        json={"role": "viewer"},
        headers=auth(make_token(sub="admin-1", role="admin")),
    )
    assert r.status_code == 400


def test_admin_cannot_deactivate_self(client):
    r = client.patch(
        "/api/v1/admin/users/admin-1",
        json={"is_active": False},
        headers=auth(make_token(sub="admin-1", role="admin")),
    )
    assert r.status_code == 400


def test_audit_log_limit_is_capped(client):
    r = client.get(
        "/api/v1/admin/audit?limit=100000", headers=auth(make_token(role="admin"))
    )
    assert r.status_code == 422


# --- ABAC span filtering ----------------------------------------------------

@pytest.fixture
def stub_traces(monkeypatch):
    """Point the traces router at in-memory rows."""

    def _install(rows):
        async def get_traces(_db, agent_name=None, limit=50, offset=0):
            page = rows[offset : offset + limit]
            return page

        async def get_trace_with_spans(trace_id, _db):
            return next((t for t in rows if t.id == trace_id), None)

        import app.routers.traces as traces_router

        monkeypatch.setattr(traces_router, "get_traces", get_traces)
        monkeypatch.setattr(traces_router, "get_trace_with_spans", get_trace_with_spans)

    return _install


def test_trace_detail_hides_spans_above_clearance(client, stub_traces):
    stub_traces([
        make_trace(spans=[
            make_span(span_id="public", sensitivity="public"),
            make_span(span_id="secret", sensitivity="confidential"),
        ])
    ])
    r = client.get(f"{TRACES}/trace-1", headers=auth(make_token(role="viewer")))
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["spans"]] == ["public"]


def test_trace_detail_forbidden_when_no_span_readable(client, stub_traces):
    stub_traces([make_trace(spans=[make_span(sensitivity="confidential")])])
    r = client.get(f"{TRACES}/trace-1", headers=auth(make_token(role="viewer")))
    assert r.status_code == 403


def test_admin_sees_every_span(client, stub_traces):
    stub_traces([
        make_trace(spans=[
            make_span(span_id="public", sensitivity="public"),
            make_span(span_id="secret", sensitivity="confidential"),
        ])
    ])
    r = client.get(f"{TRACES}/trace-1", headers=auth(make_token(role="admin", clearance_level=2)))
    assert [s["id"] for s in r.json()["spans"]] == ["public", "secret"]


def test_owner_reads_own_confidential_span(client, stub_traces):
    stub_traces([
        make_trace(spans=[make_span(sensitivity="confidential", owner_email="owner@example.com")])
    ])
    r = client.get(
        f"{TRACES}/trace-1",
        headers=auth(make_token(role="viewer", email="owner@example.com")),
    )
    assert r.status_code == 200
    assert len(r.json()["spans"]) == 1


def test_trace_list_hides_traces_with_no_readable_span(client, stub_traces):
    stub_traces([
        make_trace("visible", spans=[make_span(sensitivity="public")]),
        make_trace("hidden", spans=[make_span(sensitivity="confidential")]),
    ])
    r = client.get(TRACES, headers=auth(make_token(role="viewer")))
    assert [t["id"] for t in r.json()] == ["visible"]


def test_trace_list_returns_a_full_page_despite_unreadable_rows(client, stub_traces):
    """Filtering happens after the SQL LIMIT, so the endpoint must scan forward
    rather than hand back a short page."""
    rows = []
    for i in range(30):
        sensitivity = "confidential" if i % 2 else "public"
        rows.append(make_trace(f"trace-{i}", spans=[make_span(sensitivity=sensitivity)]))
    stub_traces(rows)

    r = client.get(f"{TRACES}?limit=5", headers=auth(make_token(role="viewer")))
    assert r.status_code == 200
    assert len(r.json()) == 5
