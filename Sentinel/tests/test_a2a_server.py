"""
Tests for the A2A FastAPI server: open-by-default behavior, optional
bearer-token gating, and lazy task TTL eviction.
"""
import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def server_module(monkeypatch):
    """Reload the server module fresh so env-var changes take effect."""
    import sentinel.a2a.server as server
    importlib.reload(server)
    yield server


def test_health_and_agent_card_open_by_default(server_module):
    client = TestClient(server_module.app)
    assert client.get("/health").status_code == 200
    assert client.get("/.well-known/agent-card.json").status_code == 200


def test_review_endpoint_open_when_no_token_configured(server_module, monkeypatch):
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    importlib.reload(server_module)
    client = TestClient(server_module.app)
    r = client.post("/a2a/review", json={"target_path": "targets/c1_clean"})
    assert r.status_code == 200
    assert "task_id" in r.json()


def test_review_endpoint_rejects_missing_token_when_configured(monkeypatch):
    monkeypatch.setenv("SENTINEL_A2A_TOKEN", "secret123")
    import sentinel.a2a.server as server
    importlib.reload(server)
    client = TestClient(server.app)
    r = client.post("/a2a/review", json={"target_path": "targets/c1_clean"})
    assert r.status_code == 401


def test_review_endpoint_accepts_correct_bearer_token(monkeypatch):
    monkeypatch.setenv("SENTINEL_A2A_TOKEN", "secret123")
    import sentinel.a2a.server as server
    importlib.reload(server)
    client = TestClient(server.app)
    r = client.post(
        "/a2a/review",
        json={"target_path": "targets/c1_clean"},
        headers={"Authorization": "Bearer secret123"},
    )
    assert r.status_code == 200


def test_stale_tasks_are_evicted(server_module, monkeypatch):
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    importlib.reload(server_module)
    server_module.TASK_TTL_SECONDS = 1

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    server_module.tasks["stale_task"] = {
        "id": "stale_task", "status": "completed", "target": "x",
        "created_at": old_time, "completed_at": old_time, "result": {},
    }

    client = TestClient(server_module.app)
    client.post("/a2a/review", json={"target_path": "targets/c1_clean"})

    assert "stale_task" not in server_module.tasks
