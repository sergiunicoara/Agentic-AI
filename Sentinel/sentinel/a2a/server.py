"""
Sentinel A2A Server.

Exposes Sentinel as a standards-compliant A2A agent:
  1. Discovery:  GET /.well-known/agent-card.json  (canonical)
                 GET /.well-known/agent.json        (compatibility alias)
  2. JSON-RPC 2.0 task protocol:  POST /a2a
     Methods: message/send, message/stream, tasks/get, tasks/cancel,
     tasks/resubscribe, plus tasks/send / tasks/sendSubscribe as
     deprecated aliases for message/send / message/stream.
  3. Deprecated REST compatibility wrappers, unchanged wire shape:
     POST /a2a/review, GET /a2a/review/{task_id}

Run with: python -m sentinel.a2a.server
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sentinel.a2a.agent_card import build_agent_card
from sentinel.a2a.auth import require_bearer_token
from sentinel.a2a.jsonrpc import (
    JsonRpcError,
    ParseError,
    dispatch,
    error_response,
    parse_request,
)
from sentinel.a2a.streaming import EventBroadcaster, sse_stream
from sentinel.a2a.task_service import TaskService
from sentinel.a2a.task_store import get_task_store
from sentinel.a2a.telemetry import configure_tracing, tracer
from sentinel.pipeline import run_sentinel

configure_tracing()

app = FastAPI(title="Sentinel A2A Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the React dashboard from /ui if the build exists (local dev or container).
_DASHBOARD_DIST = Path(__file__).parent.parent / "dashboard" / "dist"
if _DASHBOARD_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(_DASHBOARD_DIST), html=True), name="dashboard")

# Lazily built on first use, inside a running event loop (see EventBroadcaster's
# docstring for why this can't happen at import time), and reset by
# `importlib.reload(server)` in tests the same way the old module-level
# `tasks` dict used to be.
_task_service: TaskService | None = None

STREAMING_METHODS = {"message/stream", "tasks/sendSubscribe", "tasks/resubscribe"}


def get_task_service() -> TaskService:
    global _task_service
    if _task_service is None:
        _task_service = TaskService(get_task_store(), EventBroadcaster())
    return _task_service


@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """A2A discovery endpoint (canonical path) — returns Sentinel's agent card."""
    with tracer.start_as_current_span("a2a.discovery"):
        return JSONResponse(build_agent_card())


@app.get("/.well-known/agent.json")
async def get_agent_card_alias():
    """Compatibility alias for older A2A drafts that used this path."""
    with tracer.start_as_current_span("a2a.discovery"):
        return JSONResponse(build_agent_card())


@app.post("/a2a", dependencies=[Depends(require_bearer_token)])
async def a2a_rpc(request: Request):
    """The A2A JSON-RPC 2.0 endpoint."""
    body = await request.body()
    try:
        rpc_request = parse_request(body)
    except JsonRpcError as exc:
        return JSONResponse(error_response(None, exc))

    service = get_task_service()

    if rpc_request.method in STREAMING_METHODS:
        try:
            if rpc_request.method == "tasks/resubscribe":
                queue = await service.resubscribe(rpc_request.params)
            else:
                _, queue = await service.send_stream(rpc_request.params)
        except JsonRpcError as exc:
            return JSONResponse(error_response(rpc_request.id, exc))
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(error_response(rpc_request.id, ParseError(str(exc))))
        return StreamingResponse(sse_stream(queue), media_type="text/event-stream")

    handlers = {
        "message/send": service.send,
        "tasks/send": service.send,  # deprecated alias
        "tasks/get": service.get,
        "tasks/cancel": service.cancel,
        "tasks/pushNotificationConfig/set": _push_notifications_unsupported,
        "tasks/pushNotificationConfig/get": _push_notifications_unsupported,
        "tasks/pushNotificationConfig/list": _push_notifications_unsupported,
        "tasks/pushNotificationConfig/delete": _push_notifications_unsupported,
    }
    with tracer.start_as_current_span(f"a2a.rpc.{rpc_request.method}"):
        response = await dispatch(rpc_request, handlers)
    return JSONResponse(response)


async def _push_notifications_unsupported(params: dict):
    from sentinel.a2a.jsonrpc import PushNotificationNotSupportedError

    raise PushNotificationNotSupportedError(
        "Sentinel does not support push notifications (capabilities.pushNotifications is false)"
    )


class ReviewRequest(BaseModel):
    target_path: str
    include_red_team: bool = False
    task_id: str | None = None


# The legacy REST API predates the TaskState enum and used its own vocabulary.
# Translate so existing callers of /a2a/review* keep seeing the strings they
# always have ("canceled" is new — the old API had no cancellation at all).
_LEGACY_STATUS_MAP = {
    "submitted": "pending",
    "working": "running",
    "completed": "completed",
    "failed": "failed",
    "canceled": "canceled",
}


def _task_to_legacy_dict(task) -> dict:
    """Translate the new Task model back to the flat shape /a2a/review has
    always returned, so existing callers of the deprecated REST API see no
    wire-format change."""
    result = None
    if task.artifacts:
        data_parts = [p.data for p in task.artifacts[0].parts if p.data is not None]
        result = data_parts[0] if data_parts else None
    elif task.status.state.value == "failed" and task.status.message:
        text_parts = [p.text for p in task.status.message.parts if p.text]
        result = {"error": text_parts[0] if text_parts else "unknown error"}

    completed_at = task.status.timestamp if task.status.state.is_terminal else None
    return {
        "id": task.id,
        "status": _LEGACY_STATUS_MAP.get(task.status.state.value, task.status.state.value),
        "target": task.metadata.get("target_path"),
        "created_at": task.metadata.get("created_at", task.status.timestamp),
        "completed_at": completed_at,
        "result": result,
    }


@app.post("/a2a/review", dependencies=[Depends(require_bearer_token)], deprecated=True)
async def submit_review(request: ReviewRequest):
    """
    Deprecated: submit a security review task via the legacy REST shape.
    Prefer POST /a2a with the message/send JSON-RPC method.
    Returns immediately with a task_id for polling.
    """
    service = get_task_service()
    task = await service.send(
        {
            "id": request.task_id,
            "metadata": {
                "target_path": request.target_path,
                "include_red_team": request.include_red_team,
            },
        }
    )
    legacy_status = _LEGACY_STATUS_MAP.get(task.status.state.value, task.status.state.value)
    return {"task_id": task.id, "status": legacy_status, "message": "Review started"}


@app.get("/a2a/review/{task_id}", dependencies=[Depends(require_bearer_token)], deprecated=True)
async def get_review_result(task_id: str):
    """Deprecated: poll for review task results via the legacy REST shape."""
    from sentinel.a2a.jsonrpc import TaskNotFoundError

    service = get_task_service()
    try:
        task = await service.get({"id": task_id})
    except TaskNotFoundError:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return _task_to_legacy_dict(task)


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "sentinel", "version": "1.0.0"}


@app.websocket("/ws/scan")
async def ws_scan(websocket: WebSocket):
    """
    WebSocket endpoint for the live dashboard.
    Client sends: {"target_path": "...", "include_red_team": bool, "include_llm_auditor": bool}
    Server streams progress events as JSON until the scan completes.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
    except WebSocketDisconnect:
        return

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_progress(event: dict):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _run():
        try:
            await loop.run_in_executor(None, lambda: run_sentinel(
                data.get("target_path", ""),
                verbose=False,
                include_red_team=data.get("include_red_team", False),
                include_llm_auditor=data.get("include_llm_auditor", False),
                on_progress=on_progress,
            ))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait,
                                      {"type": "error", "message": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel = done

    asyncio.create_task(_run())

    # Cloud Run's front end (and some dev proxies) silently close a
    # WebSocket that carries no bytes for ~30s, regardless of the app's
    # own request timeout. Long-running stages (pip-audit querying an
    # advisory DB per dependency, semgrep on a cold cache) can go quiet
    # for well over that — so send a heartbeat on any gap longer than
    # HEARTBEAT_INTERVAL to keep the connection demonstrably alive
    # without changing the actual event stream the dashboard renders.
    HEARTBEAT_INTERVAL = 10  # seconds
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
                continue
            if event is None:
                break
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
