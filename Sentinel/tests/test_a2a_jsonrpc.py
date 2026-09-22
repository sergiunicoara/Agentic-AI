"""
Tests for the A2A JSON-RPC 2.0 endpoint (POST /a2a): envelope validation,
message/send (+ deprecated tasks/send alias), tasks/get, and auth gating.
Streaming (message/stream) is covered in tests/test_a2a_streaming.py,
cancellation in tests/test_a2a_cancel.py.

Uses `with TestClient(app) as client:` throughout — see the comment in
tests/test_a2a_server.py for why that matters whenever a test polls for a
background task's completion across more than one request.
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


def _rpc(client, method, params=None, req_id=1):
    return client.post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}},
    )


def test_missing_jsonrpc_version_is_invalid_request(server_module):
    with TestClient(server_module.app) as client:
        r = client.post("/a2a", json={"method": "tasks/get", "params": {"id": "x"}, "id": 1})
        assert r.status_code == 200  # JSON-RPC errors still return HTTP 200
        assert r.json()["error"]["code"] == -32600


def test_malformed_json_is_parse_error(server_module):
    with TestClient(server_module.app) as client:
        r = client.post("/a2a", content=b"{not json", headers={"Content-Type": "application/json"})
        assert r.json()["error"]["code"] == -32700


def test_unknown_method_returns_method_not_found(server_module):
    with TestClient(server_module.app) as client:
        r = _rpc(client, "tasks/doesNotExist", {})
        body = r.json()
        assert body["error"]["code"] == -32601
        assert body["id"] == 1


def test_message_send_without_target_is_invalid_params(server_module):
    with TestClient(server_module.app) as client:
        r = _rpc(client, "message/send", {"message": {"role": "user", "parts": []}})
        assert r.json()["error"]["code"] == -32602


def test_message_send_happy_path_reaches_completed(server_module):
    with TestClient(server_module.app) as client:
        r = _rpc(client, "message/send", {"metadata": {"target_path": "targets/c1_clean"}})
        body = r.json()
        assert "result" in body
        task = body["result"]
        assert task["status"]["state"] == "submitted"
        task_id = task["id"]

        deadline = time.time() + 60
        final_state = None
        while time.time() < deadline:
            got = _rpc(client, "tasks/get", {"id": task_id}, req_id=2)
            final_state = got.json()["result"]["status"]["state"]
            if final_state in ("completed", "failed"):
                break
            time.sleep(0.5)
        assert final_state == "completed"


def test_deprecated_tasks_send_alias_behaves_like_message_send(server_module):
    with TestClient(server_module.app) as client:
        r = _rpc(client, "tasks/send", {"metadata": {"target_path": "targets/c1_clean"}})
        assert r.json()["result"]["status"]["state"] == "submitted"


def test_tasks_get_unknown_id_returns_task_not_found(server_module):
    with TestClient(server_module.app) as client:
        r = _rpc(client, "tasks/get", {"id": "no-such-task"})
        assert r.json()["error"]["code"] == -32001


def test_push_notification_methods_return_unsupported(server_module):
    with TestClient(server_module.app) as client:
        r = _rpc(client, "tasks/pushNotificationConfig/set", {"id": "x"})
        assert r.json()["error"]["code"] == -32003


def test_rpc_endpoint_requires_token_when_configured(monkeypatch):
    server = _reloaded_server(monkeypatch, token="secret123")
    with TestClient(server.app) as client:
        unauthorized = _rpc(client, "tasks/get", {"id": "x"})
        assert unauthorized.status_code == 401

        r = client.post(
            "/a2a",
            json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}},
            headers={"Authorization": "Bearer secret123"},
        )
        assert r.status_code == 200
        assert r.json()["error"]["code"] == -32001  # authenticated, task just doesn't exist
