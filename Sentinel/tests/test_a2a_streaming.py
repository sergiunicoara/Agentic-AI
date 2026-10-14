"""
Tests for SSE task streaming (`message/stream`, `tasks/resubscribe`):
A2A-shaped frames (JSON-RPC envelopes around Task / status-update /
artifact-update events), event ordering, the final event closing the
stream, resubscribing to an already-terminal task, subscription cleanup
(after a normal end and after a client disconnect), terminal-state
polling for tasks executing elsewhere, and the stream lifetime cap.
"""
import asyncio
import importlib
import json
import threading

import httpx
import pytest

from sentinel.a2a import task_service as task_service_module
from sentinel.a2a.models import Task, TaskState, TaskStatus
from sentinel.a2a.streaming import EventBroadcaster
from sentinel.a2a.task_service import TaskService
from sentinel.a2a.task_store import InMemoryTaskStore
from sentinel.models.schemas import Attestation


def _fast_stub(target_path, verbose=False, on_progress=None, **kwargs):
    if on_progress:
        on_progress({"type": "stage", "stage": "profiling"})
        on_progress({"type": "stage", "stage": "evidence"})
    return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")


def _fresh_server(monkeypatch, stub=_fast_stub):
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    monkeypatch.setattr(task_service_module, "run_sentinel", stub)
    import sentinel.a2a.auth as auth
    import sentinel.a2a.server as server
    importlib.reload(auth)
    importlib.reload(server)
    return server


async def _collect_frames(app, payload: dict) -> list[dict]:
    """Every `data:` frame of the response, parsed (JSON-RPC envelopes)."""
    frames = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/a2a", json=payload, headers={"Accept": "text/event-stream"}, timeout=30,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    frames.append(json.loads(line[len("data:"):].strip()))
    return frames


def _stream_payload(req_id=1, **params):
    params.setdefault("metadata", {"target_path": "targets/c1_clean"})
    return {"jsonrpc": "2.0", "id": req_id, "method": "message/stream", "params": params}


def test_message_stream_frames_are_jsonrpc_responses_with_a2a_events(monkeypatch):
    server = _fresh_server(monkeypatch)
    frames = asyncio.run(_collect_frames(server.app, _stream_payload(req_id="abc")))

    for frame in frames:
        assert frame["jsonrpc"] == "2.0"
        assert frame["id"] == "abc"
        assert "result" in frame and "error" not in frame
    events = [f["result"] for f in frames]

    assert events[0]["kind"] == "task"
    assert events[0]["status"]["state"] == "submitted"
    task_id, context_id = events[0]["id"], events[0]["contextId"]
    assert context_id
    for event in events[1:]:
        assert event["kind"] in ("status-update", "artifact-update")
        assert event["taskId"] == task_id
        assert event["contextId"] == context_id

    status_updates = [e for e in events if e["kind"] == "status-update"]
    assert status_updates[0]["status"]["state"] == "working"
    assert status_updates[-1]["status"]["state"] == "completed"
    assert status_updates[-1]["final"] is True
    assert sum(1 for e in events if e.get("final")) == 1
    assert events[-1] is status_updates[-1], "nothing may follow the final event"

    # Pipeline progress rides on working status-updates as an agent data part.
    progress = [
        e for e in status_updates
        if e["status"].get("message") and e["status"]["message"]["parts"][0]["kind"] == "data"
    ]
    assert [p["status"]["message"]["parts"][0]["data"]["stage"] for p in progress] == ["profiling", "evidence"]
    assert all(p["status"]["state"] == "working" and p["final"] is False for p in progress)
    assert all(p["status"]["message"]["role"] == "agent" for p in progress)

    # The result artifact arrives as an artifact-update, before the final status.
    artifact_updates = [e for e in events if e["kind"] == "artifact-update"]
    assert len(artifact_updates) == 1
    assert artifact_updates[0]["lastChunk"] is True
    assert artifact_updates[0]["artifact"]["parts"][0]["data"]["verdict"] == "pass"
    assert events.index(artifact_updates[0]) < len(events) - 1


def test_message_stream_echoes_caller_context_id(monkeypatch):
    server = _fresh_server(monkeypatch)
    payload = _stream_payload(
        message={"role": "user", "contextId": "ctx-caller-1", "parts": [{"kind": "text", "text": "targets/c1_clean"}]},
        metadata={},
    )
    events = [f["result"] for f in asyncio.run(_collect_frames(server.app, payload))]
    assert {e.get("contextId") for e in events} == {"ctx-caller-1"}


def test_stream_releases_subscription_after_final_event(monkeypatch):
    server = _fresh_server(monkeypatch)

    async def scenario():
        await _collect_frames(server.app, _stream_payload())
        assert server.get_task_service().broadcaster.subscriber_count() == 0

    asyncio.run(scenario())


def test_resubscribe_to_terminal_task_returns_snapshot_and_final_then_closes(monkeypatch):
    server = _fresh_server(monkeypatch)

    async def scenario():
        service = server.get_task_service()
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})

        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            current = await service.get({"id": task.id})
            if current.status.state.value == "completed":
                break
            await asyncio.sleep(0.05)

        payload = {"jsonrpc": "2.0", "id": 2, "method": "tasks/resubscribe", "params": {"id": task.id}}
        events = [f["result"] for f in await _collect_frames(server.app, payload)]
        assert [e["kind"] for e in events] == ["task", "status-update"]
        assert events[0]["status"]["state"] == "completed"
        assert events[0]["artifacts"], "the snapshot carries the result artifact"
        assert events[1]["status"]["state"] == "completed"
        assert events[1]["final"] is True
        assert service.broadcaster.subscriber_count() == 0

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
        assert server.get_task_service().broadcaster.subscriber_count() == 0

    asyncio.run(scenario())


def _blocking_stub(release: threading.Event, started: threading.Event):
    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        started.set()
        release.wait(timeout=10)
        if on_progress:
            on_progress({"type": "stage", "stage": "late"})
        return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")

    return stub


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
def test_client_disconnect_mid_stream_releases_subscription(monkeypatch, spec_version):
    """Drive the ASGI app directly so the client can vanish mid-stream: with
    ASGI spec 2.4 a send to a gone client raises OSError; before 2.4,
    Starlette learns of it via an http.disconnect message."""
    release, started = threading.Event(), threading.Event()
    server = _fresh_server(monkeypatch, stub=_blocking_stub(release, started))

    async def scenario():
        body = json.dumps(_stream_payload()).encode()
        body_sent = False
        gone = asyncio.Event()

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        chunks = []

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"])
                if len(chunks) >= 2:  # snapshot + working status seen; now vanish
                    gone.set()
                    if spec_version == "2.4":
                        raise OSError("client went away")

        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": spec_version},
            "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/a2a",
            "raw_path": b"/a2a", "query_string": b"", "root_path": "",
            "headers": [(b"host", b"test"), (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode())],
            "client": ("127.0.0.1", 5555), "server": ("test", 80),
        }
        try:
            await asyncio.wait_for(server.app(scope, receive, send), timeout=10)
        except Exception:  # noqa: BLE001 - ClientDisconnect may propagate; that's the point
            pass
        service = server.get_task_service()
        assert len(chunks) >= 2
        assert service.broadcaster.subscriber_count() == 0
        # A2A semantics: a dropped stream doesn't cancel the task — the
        # client may resubscribe. Let it finish before the loop closes.
        release.set()
        task_id = json.loads(chunks[0].decode().removeprefix("data: "))["result"]["id"]
        for _ in range(200):
            if (await service.get({"id": task_id})).status.state.is_terminal:
                break
            await asyncio.sleep(0.02)
        assert (await service.get({"id": task_id})).status.state.value == "completed"

    try:
        asyncio.run(scenario())
    finally:
        release.set()


def _working_task(task_id="t-remote") -> Task:
    return Task(id=task_id, contextId="ctx-1", status=TaskStatus(state=TaskState.WORKING))


def test_stream_learns_terminal_state_from_store_when_no_event_arrives():
    """A task executing on another instance never publishes on this
    instance's broadcaster; the heartbeat poll must still end the stream."""
    async def scenario():
        store = InMemoryTaskStore()
        service = TaskService(store, EventBroadcaster(), heartbeat_interval=0.05)
        working = _working_task()
        await store.create_if_absent(working)

        stream = await service.resubscribe({"id": working.id})
        first = await stream.__anext__()
        assert first["kind"] == "task" and first["status"]["state"] == "working"

        # "Another instance" completes it directly in the shared store.
        from sentinel.a2a.models import Artifact, Part
        done = working.model_copy(
            update={"artifacts": [Artifact(name="attestation", parts=[Part(kind="data", data={"verdict": "pass"})])]}
        ).with_status(TaskState.COMPLETED)
        assert await store.transition(working.id, {TaskState.WORKING}, done)

        rest = [e async for e in stream if isinstance(e, dict)]
        assert [e["kind"] for e in rest] == ["artifact-update", "status-update"]
        assert rest[-1]["final"] is True and rest[-1]["status"]["state"] == "completed"
        assert service.broadcaster.subscriber_count() == 0

    asyncio.run(scenario())


def test_stream_ends_at_max_lifetime_for_orphaned_task():
    async def scenario():
        store = InMemoryTaskStore()
        service = TaskService(store, EventBroadcaster(), heartbeat_interval=0.05, stream_max_seconds=0.3)
        await store.create_if_absent(_working_task("orphan"))
        stream = await service.resubscribe({"id": "orphan"})
        events = await asyncio.wait_for(_drain(stream), timeout=5)
        assert events[0]["kind"] == "task"
        assert not any(isinstance(e, dict) and e.get("final") for e in events)
        assert service.broadcaster.subscriber_count() == 0

    asyncio.run(scenario())


async def _drain(stream):
    return [e async for e in stream]


def test_broadcaster_drops_task_entry_after_final_event():
    async def scenario():
        broadcaster = EventBroadcaster()
        q1, q2 = broadcaster.subscribe("t"), broadcaster.subscribe("t")
        broadcaster.publish("t", {"kind": "status-update", "final": False})
        broadcaster.publish("t", {"kind": "status-update", "final": True})
        await asyncio.sleep(0)  # let call_soon_threadsafe callbacks run
        await asyncio.sleep(0)
        assert broadcaster.subscriber_count() == 0
        assert q1.qsize() == q2.qsize() == 2
        broadcaster.unsubscribe("t", q1)  # late unsubscribe is a harmless no-op

    asyncio.run(scenario())


def test_unstarted_stream_releases_subscription_on_aclose():
    async def scenario():
        store = InMemoryTaskStore()
        service = TaskService(store, EventBroadcaster())
        await store.create_if_absent(_working_task("never-read"))
        stream = service.open_stream("never-read")
        assert service.broadcaster.subscriber_count("never-read") == 1
        await stream.aclose()
        assert service.broadcaster.subscriber_count() == 0

    asyncio.run(scenario())
