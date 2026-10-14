"""
Event fan-out for A2A task streaming (`message/stream`, `tasks/resubscribe`)
and the dashboard's `/ws/scan` WebSocket.

Events published here are A2A event objects (the `result` of a streaming
JSON-RPC response): a `Task` snapshot, `TaskStatusUpdateEvent`
(`kind: "status-update"`), or `TaskArtifactUpdateEvent`
(`kind: "artifact-update"`). `sse_stream` wraps each one in a JSON-RPC 2.0
response envelope carrying the originating request's id, which is what
A2A clients parse out of every `data:` line. `/ws/scan` consumes the same
events and translates them back to the dashboard's own message shape.

Because subscriber bookkeeping and publishing both funnel through
`call_soon_threadsafe` onto the single event loop, `publish()` is safe to
call from the worker thread that runs the (blocking) Sentinel pipeline.

Subscriptions are released on every path out of a stream (`EventStream`
unsubscribes when it ends or is closed), and the broadcaster drops a
task's whole subscriber list once its final event is delivered — nothing
is ever published for a task after that, so keeping the queues would
only leak them.

Limitation: fan-out is per-process. If a task's execution and a client's
`tasks/resubscribe` call land on different instances (multi-instance Redis
deployment), the resubscribing instance relays no in-flight events; the
stream instead polls the durable store on every heartbeat and emits the
terminal events itself once the task finishes (see TaskService).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Callable

# Yielded by an EventStream when nothing happened for a heartbeat interval.
# Each transport renders it in its own keep-alive form (an SSE comment line,
# a {"type": "heartbeat"} WebSocket message).
HEARTBEAT = object()


def sse_format(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def sse_stream(events: "EventStream", request_id: Any):
    """Render `events` as SSE frames, each a JSON-RPC 2.0 response to
    `request_id`, plus comment-line heartbeats so idle proxies (Cloud Run)
    don't close the connection. Always releases the subscription."""
    try:
        async for event in events:
            if event is HEARTBEAT:
                yield ": heartbeat\n\n"
                continue
            yield sse_format({"jsonrpc": "2.0", "id": request_id, "result": event})
    finally:
        await events.aclose()


class EventBroadcaster:
    def __init__(self):
        # Must be constructed from within a running event loop (e.g. lazily
        # on first use from a route handler) so this is the loop uvicorn is
        # actually serving requests on, not an incidental one created at
        # module-import time.
        self._loop = asyncio.get_running_loop()
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(task_id, []).append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(task_id)
        if subs and queue in subs:
            subs.remove(queue)
            if not subs:
                del self._subscribers[task_id]

    def subscriber_count(self, task_id: str | None = None) -> int:
        if task_id is not None:
            return len(self._subscribers.get(task_id, []))
        return sum(len(subs) for subs in self._subscribers.values())

    def publish(self, task_id: str, event: dict) -> None:
        """Thread-safe — may be called from the worker thread executing the task."""
        try:
            self._loop.call_soon_threadsafe(self._publish_on_loop, task_id, event)
        except RuntimeError:
            # Loop already closed (process shutting down) — nobody is left to
            # receive the event.
            pass

    def _publish_on_loop(self, task_id: str, event: dict) -> None:
        subs = self._subscribers.get(task_id, [])
        for queue in subs:
            queue.put_nowait(event)
        if event.get("final"):
            # Every current subscriber now holds the final event in its queue;
            # no further event can follow it, so the entry is dead weight.
            self._subscribers.pop(task_id, None)


class EventStream:
    """One subscriber's async-iterable view of a task's events.

    Subscribes eagerly, at construction, so nothing published after this
    object exists can be missed (the iterator body may not start running
    until the HTTP response begins streaming). Releases the subscription
    when iteration ends or on `aclose()` — including when iteration never
    started, which a bare async generator's `finally` can't cover.
    """

    def __init__(
        self,
        broadcaster: EventBroadcaster,
        task_id: str,
        produce: Callable[[asyncio.Queue], AsyncIterator[Any]],
    ):
        self._broadcaster = broadcaster
        self.task_id = task_id
        self._queue = broadcaster.subscribe(task_id)
        self._events = produce(self._queue)
        self._closed = False

    def __aiter__(self) -> "EventStream":
        return self

    async def __anext__(self) -> Any:
        try:
            return await self._events.__anext__()
        except StopAsyncIteration:
            self._release()
            raise

    def _release(self) -> None:
        self._broadcaster.unsubscribe(self.task_id, self._queue)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._events.aclose()
        finally:
            self._release()
