from fastapi.testclient import TestClient

from app.server import app


client = TestClient(app)


def test_health():
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_match_basic():
    payload = {"text": "We are hiring an AI/ML engineer to build production agents."}
    r = client.post("/api/v1/match", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["job"]["text"] == payload["text"]
    assert "summary" in data
