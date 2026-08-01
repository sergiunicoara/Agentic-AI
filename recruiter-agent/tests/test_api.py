from fastapi.testclient import TestClient

from app.server import app
from app.security import reset_rate_limits


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "recruiter-agent"
    assert "session_store" in data


def test_health_returns_json_not_frontend():
    """Regression: the frontend catch-all GET /{path:path} used to be
    registered before the API GET routes, shadowing them all — /health
    returned index.html instead of JSON. It must stay the last route."""
    r = client.get("/health")
    assert r.headers["content-type"].startswith("application/json")


def _internal_headers(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    reset_rate_limits()
    return {"X-Internal-Api-Key": "test-internal-key"}


def test_mcp_tools_require_internal_access(monkeypatch):
    _internal_headers(monkeypatch)
    r = client.get("/mcp/tools")
    assert r.status_code == 401


def test_mcp_tools_not_shadowed(monkeypatch):
    """GET /mcp/tools must return the tool list, not the frontend."""
    r = client.get("/mcp/tools", headers=_internal_headers(monkeypatch))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


def test_mcp_json_rpc_tool_discovery(monkeypatch):
    r = client.post(
        "/mcp",
        headers=_internal_headers(monkeypatch),
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["id"] == 1
    assert any(tool["name"] == "judge_recruiter_turn" for tool in data["result"]["tools"])


def test_internal_rate_limit(monkeypatch):
    headers = _internal_headers(monkeypatch)
    monkeypatch.setenv("INTERNAL_API_RATE_LIMIT_PER_MINUTE", "1")
    assert client.get("/mcp/tools", headers=headers).status_code == 200
    assert client.get("/mcp/tools", headers=headers).status_code == 429


def test_unknown_path_serves_frontend():
    """The catch-all still works for non-API paths."""
    r = client.get("/some/unknown/spa-route")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_chat_basic():
    payload = {"session_id": "test-api-chat", "message": "Senior ML Engineer"}
    r = client.post("/chat", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert data["reply"]  # non-empty


def test_chat_schedules_automatic_critic_validation(monkeypatch):
    calls = []
    monkeypatch.setenv("AUTO_VALIDATE_REPLIES", "true")
    monkeypatch.setattr(
        "app.server.validate_turn",
        lambda **kwargs: calls.append(kwargs) or {"verdict": "PASS"},
    )

    r = client.post(
        "/chat",
        json={"session_id": "test-auto-validation", "message": "AI Engineer"},
    )

    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["session_id"] == "test-auto-validation"
