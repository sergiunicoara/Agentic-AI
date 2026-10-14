"""
Sentinel A2A Server.

Exposes Sentinel as a standards-compliant A2A agent:
  1. Discovery:  GET /.well-known/agent-card.json  (canonical)
                 GET /.well-known/agent.json        (compatibility alias)
  2. JSON-RPC 2.0 task protocol:  POST /a2a
     Methods: message/send, message/stream, tasks/get, tasks/cancel,
     tasks/resubscribe, plus tasks/send / tasks/sendSubscribe as
     deprecated aliases for message/send / message/stream.
     Batches and notifications follow JSON-RPC 2.0; streaming methods
     must be sent as a single request (they answer with an SSE stream).
  3. Deprecated REST compatibility wrappers, unchanged wire shape:
     POST /a2a/review, GET /a2a/review/{task_id}
  4. GET /ws/scan — the dashboard's live-progress WebSocket.

Every scan-starting route (including /ws/scan) requires SENTINEL_A2A_TOKEN
when it is set and runs through the shared TaskService, so concurrency
limits and cancel semantics are the same everywhere.

Run with: python -m sentinel.a2a.server
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sentinel.a2a import auth, limits
from sentinel.a2a.agent_card import build_agent_card
from sentinel.a2a.auth import bearer_value, require_bearer_token
from sentinel.a2a.jsonrpc import (
    InvalidRequestError,
    JsonRpcError,
    PushNotificationNotSupportedError,
    RequestTooLargeError,
    dispatch,
    error_response,
    internal_error,
    parse_body,
    request_id_of,
    validate_request,
)
from sentinel.a2a.streaming import HEARTBEAT, EventStream, sse_stream
from sentinel.a2a.task_service import TaskService
from sentinel.a2a.task_store import get_task_store
from sentinel.a2a.telemetry import configure_tracing, tracer

configure_tracing()


def _allowed_origins() -> list[str]:
    """Browser origins trusted for CORS and for the /ws/scan Origin check:
    the Vite dev servers by default (or SENTINEL_ALLOWED_ORIGINS, comma-
    separated), plus the origin of SENTINEL_PUBLIC_URL when it is set."""
    import os

    configured = os.environ.get("SENTINEL_ALLOWED_ORIGINS")
    if configured:
        origins = [o.strip().rstrip("/") for o in configured.split(",") if o.strip()]
    else:
        origins = ["http://localhost:5173", "http://localhost:5174"]
    public_url = os.environ.get("SENTINEL_PUBLIC_URL")
    if public_url:
        parsed = urlsplit(public_url)
        if parsed.scheme and parsed.netloc:
            origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return origins


ALLOWED_ORIGINS = _allowed_origins()
MAX_BODY_BYTES = limits.max_body_bytes()


class _BodySizeLimit:
    """Reject request bodies over MAX_BODY_BYTES before they are buffered.

    A declared Content-Length over the cap is refused up front. Chunked
    bodies are counted as they arrive; crossing the cap raises a 413
    HTTPException from inside `receive`, which FastAPI re-raises as-is
    (and a2a_rpc turns into a JSON-RPC error)."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > self.max_bytes:
                response = _too_large_response(scope.get("path", ""))
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="Request body too large")
            return message

        await self.app(scope, limited_receive, send)


def _too_large_response(path: str) -> JSONResponse:
    if path == "/a2a":
        return JSONResponse(error_response(None, RequestTooLargeError()), status_code=413)
    return JSONResponse({"detail": "Request body too large"}, status_code=413)


app = FastAPI(title="Sentinel A2A Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(_BodySizeLimit, max_bytes=MAX_BODY_BYTES)

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
        from sentinel.a2a.streaming import EventBroadcaster

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


class _SSEResponse(StreamingResponse):
    """StreamingResponse that always releases the stream's subscription.

    Starlette doesn't close the body iterator when the client disconnects
    mid-stream (or when the response never starts), so an async generator's
    `finally` alone would leave the subscriber queue registered until GC."""

    def __init__(self, events: EventStream, request_id):
        super().__init__(
            sse_stream(events, request_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._events = events

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self.body_iterator.aclose()
            finally:
                await self._events.aclose()


def _rpc_handlers(service: TaskService) -> dict:
    return {
        "message/send": service.send,
        "tasks/send": service.send,  # deprecated alias
        "tasks/get": service.get,
        "tasks/cancel": service.cancel,
        "tasks/pushNotificationConfig/set": _push_notifications_unsupported,
        "tasks/pushNotificationConfig/get": _push_notifications_unsupported,
        "tasks/pushNotificationConfig/list": _push_notifications_unsupported,
        "tasks/pushNotificationConfig/delete": _push_notifications_unsupported,
    }


def _looks_like_notification(raw) -> bool:
    """A structurally valid request object without an "id" member. Errors in
    such a request (e.g. bad params) are swallowed, as JSON-RPC requires."""
    return (
        isinstance(raw, dict)
        and "id" not in raw
        and raw.get("jsonrpc") == "2.0"
        and isinstance(raw.get("method"), str)
    )


async def _handle_unary(service: TaskService, raw) -> dict | None:
    """Handle one non-streaming request object; None means "send nothing"."""
    try:
        rpc_request = validate_request(raw)
    except JsonRpcError as exc:
        return None if _looks_like_notification(raw) else error_response(request_id_of(raw), exc)

    if rpc_request.method in STREAMING_METHODS:
        response = error_response(
            rpc_request.id,
            InvalidRequestError(f"{rpc_request.method} must be sent as a single request with an id"),
        )
    else:
        handlers = _rpc_handlers(service)
        span = rpc_request.method if rpc_request.method in handlers else "unknown"
        with tracer.start_as_current_span(f"a2a.rpc.{span}"):
            response = await dispatch(rpc_request, handlers)
    return None if rpc_request.is_notification else response


async def _open_stream_response(service: TaskService, rpc_request) -> Response:
    try:
        if rpc_request.method == "tasks/resubscribe":
            stream = await service.resubscribe(rpc_request.params)
        else:
            _, stream = await service.send_stream(rpc_request.params)
    except JsonRpcError as exc:
        return JSONResponse(error_response(rpc_request.id, exc))
    except Exception as exc:  # noqa: BLE001 - a bug here is a server fault, not the caller's JSON
        return JSONResponse(error_response(rpc_request.id, internal_error(exc, rpc_request.method)))
    return _SSEResponse(stream, rpc_request.id)


@app.post("/a2a", dependencies=[Depends(require_bearer_token)])
async def a2a_rpc(request: Request):
    """The A2A JSON-RPC 2.0 endpoint."""
    try:
        body = await request.body()
    except HTTPException as exc:
        if exc.status_code == 413:
            return _too_large_response("/a2a")
        raise
    try:
        items, is_batch = parse_body(body)
    except JsonRpcError as exc:
        return JSONResponse(error_response(None, exc))

    service = get_task_service()

    if not is_batch:
        raw = items[0]
        if (
            isinstance(raw, dict)
            and raw.get("method") in STREAMING_METHODS
            and "id" in raw
        ):
            try:
                rpc_request = validate_request(raw)
            except JsonRpcError as exc:
                return JSONResponse(error_response(request_id_of(raw), exc))
            return await _open_stream_response(service, rpc_request)
        response = await _handle_unary(service, raw)
        return Response(status_code=204) if response is None else JSONResponse(response)

    responses = [r for r in [await _handle_unary(service, raw) for raw in items] if r is not None]
    return JSONResponse(responses) if responses else Response(status_code=204)


async def _push_notifications_unsupported(params: dict):
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
    try:
        task = await service.send(
            {
                "id": request.task_id,
                "metadata": {
                    "target_path": request.target_path,
                    "include_red_team": request.include_red_team,
                },
            }
        )
    except JsonRpcError as exc:
        status = 503 if exc.code == -32050 else 400
        return JSONResponse({"error": exc.message}, status_code=status)
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


# ---- /ws/scan ---------------------------------------------------------------

# Browsers can't set an Authorization header on a WebSocket, so the token may
# also arrive as `?token=` or as a `bearer.<token>` subprotocol. A browser
# client should offer ["sentinel", "bearer.<token>"]; the server then echoes
# "sentinel", so the token is never reflected back in a response header.
WS_SUBPROTOCOL = "sentinel"
_WS_TOKEN_SUBPROTOCOL_PREFIX = "bearer."
_WS_FIRST_MESSAGE_TIMEOUT = 30  # seconds
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
# RFC 6455 close code 1008: policy violation.
_WS_POLICY_VIOLATION = 1008


def _ws_credentials(websocket: WebSocket) -> tuple[str | None, str | None]:
    """Return (presented token, subprotocol to accept with)."""
    offered = [
        p.strip()
        for p in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if p.strip()
    ]
    echo = WS_SUBPROTOCOL if WS_SUBPROTOCOL in offered else None
    token = bearer_value(websocket.headers.get("authorization")) or websocket.query_params.get("token")
    if token is None:
        for proto in offered:
            if proto.startswith(_WS_TOKEN_SUBPROTOCOL_PREFIX):
                token = proto[len(_WS_TOKEN_SUBPROTOCOL_PREFIX):]
                # A browser fails the handshake unless one offered protocol
                # is echoed; fall back to this one if "sentinel" wasn't offered.
                echo = echo or proto
                break
    return token, echo


def _ws_origin_allowed(websocket: WebSocket) -> bool:
    """CORS doesn't apply to WebSockets, so cross-site pages could otherwise
    drive /ws/scan from a victim's browser (cross-site WebSocket hijacking).

    - Origin in ALLOWED_ORIGINS: allowed.
    - Same origin as the Host header (the dashboard served from /ui): allowed
      when a token is configured, or for a loopback host. Without a token, a
      non-loopback same-origin match is exactly what a DNS-rebinding page
      produces, so it isn't trusted on its own.
    - No Origin (non-browser client): allowed when a token is configured (it
      was already verified), or when the peer is on loopback.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        client_host = websocket.client.host if websocket.client else ""
        return auth.token_required() or client_host in _LOOPBACK_HOSTS
    origin = origin.rstrip("/")
    if origin in ALLOWED_ORIGINS:
        return True
    parsed = urlsplit(origin)
    host_header = websocket.headers.get("host", "")
    if not parsed.scheme or not parsed.netloc or parsed.netloc.lower() != host_header.lower():
        return False
    return auth.token_required() or (parsed.hostname or "") in _LOOPBACK_HOSTS


def _result_from_artifacts(artifacts) -> dict | None:
    for artifact in artifacts or []:
        for part in artifact.get("parts", []):
            if part.get("data") is not None:
                return part["data"]
    return None


def _status_text(status: dict) -> str | None:
    for part in (status.get("message") or {}).get("parts", []):
        if part.get("text"):
            return part["text"]
    return None


async def _pump_ws_events(websocket: WebSocket, stream: EventStream) -> None:
    """Translate A2A task events back into the dashboard's message shape:
    raw pipeline progress dicts, then {"type": "complete", ...} or
    {"type": "error", ...}, with {"type": "heartbeat"} keep-alives."""
    result = None
    complete_sent = False
    async for event in stream:
        if event is HEARTBEAT:
            await websocket.send_json({"type": "heartbeat"})
            continue
        kind = event.get("kind")
        if kind == "task":
            result = _result_from_artifacts(event.get("artifacts")) or result
        elif kind == "artifact-update":
            result = _result_from_artifacts([event.get("artifact")]) or result
        elif kind == "status-update":
            status = event.get("status", {})
            if not event.get("final"):
                for part in (status.get("message") or {}).get("parts", []):
                    if part.get("data") is not None:
                        complete_sent = complete_sent or part["data"].get("type") == "complete"
                        await websocket.send_json(part["data"])
                continue
            state = status.get("state")
            if state == "completed" and not complete_sent:
                # The adjudicator normally emits "complete" itself; synthesize
                # it from the artifact if this pipeline path didn't.
                await websocket.send_json({"type": "complete", **(result or {})})
            elif state == "failed":
                await websocket.send_json({"type": "error", "message": _status_text(status) or "Scan failed"})
            elif state == "canceled":
                await websocket.send_json({"type": "error", "message": "Scan canceled"})


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@app.websocket("/ws/scan")
async def ws_scan(websocket: WebSocket):
    """
    WebSocket endpoint for the live dashboard.
    Client sends: {"target_path": "...", "include_red_team": bool, "include_llm_auditor": bool}
    Server streams progress events as JSON until the scan completes.

    Auth and Origin are checked before the handshake is accepted (a
    rejected client sees close code 1008). The scan runs as an ordinary
    A2A task, so it counts against the same concurrency/active-task limits,
    and it is canceled if the client disconnects before it finishes.
    """
    token, subprotocol = _ws_credentials(websocket)
    if not auth.token_matches(token) or not _ws_origin_allowed(websocket):
        await websocket.close(code=_WS_POLICY_VIOLATION)
        return

    await websocket.accept(subprotocol=subprotocol)
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=_WS_FIRST_MESSAGE_TIMEOUT)
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, KeyError):
        await _close_quietly(websocket)
        return
    if not isinstance(data, dict):
        await websocket.send_json({"type": "error", "message": "Expected a JSON object"})
        await _close_quietly(websocket)
        return

    service = get_task_service()
    metadata = {k: data[k] for k in ("target_path", "include_red_team", "include_llm_auditor") if k in data}
    try:
        task, stream = await service.send_stream({"metadata": metadata})
    except JsonRpcError as exc:
        await websocket.send_json({"type": "error", "message": exc.message})
        await _close_quietly(websocket)
        return

    pump = asyncio.create_task(_pump_ws_events(websocket, stream))
    watch = asyncio.create_task(_wait_for_disconnect(websocket))
    try:
        # Cloud Run's front end (and some dev proxies) silently close a
        # WebSocket that carries no bytes for ~30s; the stream's heartbeats
        # (every TaskService.heartbeat_interval) keep it demonstrably alive.
        done, _ = await asyncio.wait({pump, watch}, return_when=asyncio.FIRST_COMPLETED)
        if pump in done:
            await _close_quietly(websocket)
    finally:
        for t in (pump, watch):
            t.cancel()
        await asyncio.gather(pump, watch, return_exceptions=True)
        await stream.aclose()
        # No-op when the scan already finished; otherwise the client left (or
        # the stream hit its lifetime cap) and nobody will read the result.
        try:
            await service.cancel_if_active(task.id)
        except Exception:  # noqa: BLE001 - best effort during teardown
            pass


async def _close_quietly(websocket: WebSocket) -> None:
    try:
        await websocket.close()
    except Exception:  # noqa: BLE001 - already closed by the peer
        pass


def check_deployment_config() -> None:
    """Fail fast on a publicly reachable but unauthenticated deployment.

    Without SENTINEL_A2A_TOKEN the A2A endpoints are open, which is fine for
    local use. Once SENTINEL_PUBLIC_URL points anywhere but the localhost
    default — or the process is running on Cloud Run (K_SERVICE is set),
    which is internet-facing whether or not the public URL was configured —
    refuse to start unless a token is set or the operator opts out
    explicitly with SENTINEL_A2A_ALLOW_UNAUTHENTICATED=1. Warn when the card
    would advertise the localhost default, which remote callers can't reach.
    """
    import logging
    import os

    from sentinel.a2a.agent_card import DEFAULT_PUBLIC_URL

    public_url = os.environ.get("SENTINEL_PUBLIC_URL")
    on_cloud_run = bool(os.environ.get("K_SERVICE"))
    public_url_set = public_url is not None and public_url != DEFAULT_PUBLIC_URL
    if not public_url_set:
        logging.getLogger("sentinel.a2a").warning(
            "SENTINEL_PUBLIC_URL is unset; the agent card advertises %s, "
            "which remote callers cannot reach.",
            DEFAULT_PUBLIC_URL,
        )
        if not on_cloud_run:
            return
    if not os.environ.get("SENTINEL_A2A_TOKEN") and os.environ.get("SENTINEL_A2A_ALLOW_UNAUTHENTICATED") != "1":
        reason = "SENTINEL_PUBLIC_URL is set" if public_url_set else "running on Cloud Run (K_SERVICE is set)"
        raise SystemExit(
            f"Refusing to start: {reason} but SENTINEL_A2A_TOKEN is not. "
            "Set a token, or set SENTINEL_A2A_ALLOW_UNAUTHENTICATED=1 to run open on purpose."
        )


if __name__ == "__main__":
    import uvicorn

    check_deployment_config()
    uvicorn.run(app, host="0.0.0.0", port=8080)
