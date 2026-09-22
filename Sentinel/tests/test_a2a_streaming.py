"""
Tests for SSE task streaming (`message/stream`, `tasks/resubscribe`):
event ordering, the final event closing the stream, and resubscribing to
an already-terminal task.
"""
import asyncio
import importlib
import json

import httpx

from sentinel.a2a import task_service as task_service_module
from sentinel.models.schemas import Attestation


def _fast_stub(target_path, verbose=False, on_progress=None, **kwargs):
    if on_progress:
        on_progress({"type": "stage", "stage": "profiling"})
        on_progress({"type": "stage", "stage": "evidence"})
    return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")


def _fresh_server(monkeypatch):
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    monkeypatch.setattr(task_service_module, "run_sentinel", _fast_stub)
    import sentinel.a2a.auth as auth
    import sentinel.a2a.server as server
    importlib.reload(auth)
    importlib.reload(server)
    return server


async def _collect_stream_events(app, payload: dict) -> list[dict]:
    events = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/a2a", json=payload, headers={"Accept": "text/event-stream"}, timeout=30,
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                event = json.loads(line[len("data:"):].strip())
                events.append(event)
                if event.get("final"):
                    break
    return events


def test_message_stream_emits_ordered_events_and_closes(monkeypatch):
    server = _fresh_server(monkeypatch)
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "message/stream",
        "params": {"metadata": {"target_path": "targets/c1_clean"}},
    }
    events = asyncio.run(_collect_stream_events(server.app, payload))

    states = [e["status"]["state"] for e in events if "status" in e]
    assert states[0] == "submitted"
    assert "working" in states
    assert states[-1] == "completed"
    assert events[-1]["final"] is True
    # nothing should follow the final event
    assert sum(1 for e in events if e.get("final")) == 1


def test_resubscribe_to_terminal_task_immediately_returns_final_event(monkeypatch):
    server = _fresh_server(monkeypatch)

    async def scenario():
        service = server.get_task_service()
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})

        deadline = asyncio.get_event_loop().time() + 10
        while asyncio.get_event_loop().time() < deadline:
            current = await service.get({"id": task.id})
            if current.status.state.value == "completed":
                break
            await asyncio.sleep(0.05)

        payload = {
            "jsonrpc": "2.0", "id": 2, "method": "tasks/resubscribe",
            "params": {"id": task.id},
        }
        events = await _collect_stream_events(server.app, payload)
        assert len(events) == 1
        assert events[0]["status"]["state"] == "completed"
        assert events[0]["final"] is True

    asyncio.run(scenario())


def test_resubscribe_to_unknown_task_returns_task_not_found(monkeypatch):
    server = _fresh_server(monkeypatch)

    async def scenario():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/a2a",
                json={"jsonrpc": "2.0", "id": 1, "method": "tasks/resubscribe", "params": {"id": "nope"}},
                headers={"Accept": "text/event-stream"},
            )
            assert r.json()["error"]["code"] == -32001

    asyncio.run(scenario())
