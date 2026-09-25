"""Regression tests for app.nl_query.service.run_nl_query's error handling.

Two bugs fixed together:
1. A validation rejection (the `except NLQueryError: raise` branch) never
   set the local `error` variable, so write_audit_log's `error` column
   recorded None for the entire class of failure most worth auditing —
   validate_intent() rejecting a filter value that tripped the injection-
   keyword guard, for instance.
2. A genuine execution failure embedded the raw exception's text directly
   into the client-facing NLQueryError message (`f"Query execution
   failed: {exc}"`), which app/api/main.py turns straight into the HTTP
   response body — a real information-disclosure path (table/column
   names, SQL fragments, provider error details).

Verified against a real Postgres instance separately (see the commit for
this fix); these tests pin the same behavior against a mocked audit-log
write so they run without a database.
"""
from __future__ import annotations

import pytest

import app.nl_query.service as svc
from app.nl_query.intent import QueryIntent
from app.nl_query.service import NLQueryError, run_nl_query


@pytest.fixture(autouse=True)
def _capture_audit_log(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(svc, "write_audit_log", lambda **kwargs: calls.append(kwargs))
    return calls


def test_validation_rejection_is_captured_in_the_audit_log(monkeypatch, _capture_audit_log):
    monkeypatch.setattr(svc, "extract_intent", lambda q: QueryIntent(table="pg_shadow", filters=[]))

    with pytest.raises(NLQueryError) as exc_info:
        run_nl_query("show me something bad", "demo")

    assert exc_info.value.status_code == 400
    assert "pg_shadow" in exc_info.value.message  # validation errors are safe/useful to show

    assert len(_capture_audit_log) == 1
    assert _capture_audit_log[0]["error"] is not None
    assert "pg_shadow" in _capture_audit_log[0]["error"]


def test_execution_failure_does_not_leak_raw_exception_to_the_client(monkeypatch, _capture_audit_log):
    monkeypatch.setattr(svc, "extract_intent", lambda q: QueryIntent(table="document", filters=[]))
    monkeypatch.setattr(svc, "validate_intent", lambda intent: type("V", (), {"ok": True})())
    monkeypatch.setattr(svc, "build_sql", lambda intent, ws: ("SELECT 1", {}))

    def _boom(sql, params, workspace_id):
        raise RuntimeError("relation \"internal_secret_table\" does not exist, pool exhausted for user 'app'")

    monkeypatch.setattr(svc, "execute_query", _boom)

    captured_events = []
    monkeypatch.setattr(svc, "emit_event", lambda name, payload: captured_events.append((name, payload)))

    with pytest.raises(NLQueryError) as exc_info:
        run_nl_query("how many documents", "demo")

    assert exc_info.value.status_code == 500
    assert "internal_secret_table" not in exc_info.value.message
    assert "pool exhausted" not in exc_info.value.message

    # Full detail still reaches the audit log and an operator-facing event.
    assert "internal_secret_table" in _capture_audit_log[0]["error"]
    assert any(
        name == "nl_query_execution_failed" and "internal_secret_table" in payload.get("error", "")
        for name, payload in captured_events
    )
