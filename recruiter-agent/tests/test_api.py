from fastapi.testclient import TestClient

from app.server import app


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


def test_mcp_tools_not_shadowed():
    """GET /mcp/tools must return the tool list, not the frontend."""
    r = client.get("/mcp/tools")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


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
