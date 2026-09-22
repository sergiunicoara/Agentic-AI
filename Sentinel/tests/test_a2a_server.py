"""
Tests for the deprecated legacy REST wrappers (/a2a/review*): open-by-default
behavior, optional bearer-token gating, TTL eviction, and idempotency gained
from routing through the shared task service. Task-store internals moved to
tests/test_a2a_persistence.py; JSON-RPC protocol tests are in
tests/test_a2a_jsonrpc.py.

Every test uses `with TestClient(app) as client:` rather than a bare
`TestClient(app)` — the fire-and-forget background task that executes a
submitted review (`asyncio.create_task` in task_service.py, matching the
pattern `/ws/scan` already used) only keeps progressing between separate
client calls when the test client's ASGI portal/event loop is kept alive
across the `with` block; a bare `TestClient(app)` call re-enters per
request and orphans anything scheduled outside that single request.
"""
import importlib
import time

import pytest
from fastapi.testclient import TestClient


def _reloaded_server(monkeypatch, token: str | None = None):
    if token:
        monkeypatch.setenv("SENTINEL_A2A_TOKEN", token)
    else:
        monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    import sentinel.a2a.auth as auth
    import sentinel.a2a.server as server
    importlib.reload(auth)
    importlib.reload(server)
    return server


@pytest.fixture
def server_module(monkeypatch):
    yield _reloaded_server(monkeypatch)


def test_health_and_agent_card_open_by_default(server_module):
    with TestClient(server_module.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/.well-known/agent-card.json").status_code == 200


def test_review_endpoint_open_when_no_token_configured(server_module):
    with TestClient(server_module.app) as client:
        r = client.post("/a2a/review", json={"target_path": "targets/c1_clean"})
        assert r.status_code == 200
        assert "task_id" in r.json()
        assert r.json()["status"] == "pending"


def test_review_endpoint_rejects_missing_token_when_configured(monkeypatch):
    server = _reloaded_server(monkeypatch, token="secret123")
    with TestClient(server.app) as client:
        r = client.post("/a2a/review", json={"target_path": "targets/c1_clean"})
        assert r.status_code == 401


def test_review_endpoint_accepts_correct_bearer_token(monkeypatch):
    server = _reloaded_server(monkeypatch, token="secret123")
    with TestClient(server.app) as client:
        r = client.post(
            "/a2a/review",
            json={"target_path": "targets/c1_clean"},
            headers={"Authorization": "Bearer secret123"},
        )
        assert r.status_code == 200


def test_review_result_endpoint_polls_and_completes(server_module):
    with TestClient(server_module.app) as client:
        submit = client.post("/a2a/review", json={"target_path": "targets/c1_clean"})
        task_id = submit.json()["task_id"]

        deadline = time.time() + 60
        result = None
        while time.time() < deadline:
            r = client.get(f"/a2a/review/{task_id}")
            assert r.status_code == 200
            result = r.json()
            if result["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)

        assert result is not None
        assert result["status"] == "completed"
        assert result["result"]["verdict"] in ("pass", "pass_with_findings", "fail")


def test_review_result_endpoint_404_for_unknown_task(server_module):
    with TestClient(server_module.app) as client:
        r = client.get("/a2a/review/does-not-exist")
        assert r.status_code == 404


def test_resubmitting_same_task_id_is_idempotent(server_module, monkeypatch):
    calls = []
    import sentinel.a2a.task_service as task_service

    real_run_sentinel = task_service.run_sentinel

    def counting_run_sentinel(*args, **kwargs):
        calls.append(1)
        return real_run_sentinel(*args, **kwargs)

    monkeypatch.setattr(task_service, "run_sentinel", counting_run_sentinel)

    with TestClient(server_module.app) as client:
        first = client.post(
            "/a2a/review", json={"target_path": "targets/c1_clean", "task_id": "fixed-id"}
        )
        second = client.post(
            "/a2a/review", json={"target_path": "targets/c1_clean", "task_id": "fixed-id"}
        )
        assert first.json()["task_id"] == second.json()["task_id"] == "fixed-id"

        deadline = time.time() + 30
        while time.time() < deadline and not calls:
            time.sleep(0.2)
        time.sleep(0.5)  # let it fully finish so a second call couldn't sneak in
        assert len(calls) == 1
