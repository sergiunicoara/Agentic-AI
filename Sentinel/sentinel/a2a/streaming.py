"""
SSE fan-out for A2A task streaming (`message/stream`, `tasks/resubscribe`).

This is a separate, in-process broadcaster from the dashboard's `/ws/scan`
WebSocket — the two are intentionally not unified. `/ws/scan` stays exactly
as it was; this module only serves the new JSON-RPC streaming methods.

Because subscriber bookkeeping and publishing both funnel through
`call_soon_threadsafe` onto the single event loop, `publish()` is safe to
call from the worker thread that runs the (blocking) Sentinel pipeline.

Limitation: fan-out is per-process. If a task's execution and a client's
`tasks/resubscribe` call land on different instances (multi-instance Redis
deployment), the resubscribing instance has no in-flight events to relay
until the task reaches a terminal state, at which point `tasks/get` (backed
by the durable store) is always authoritative regardless of which instance
serves it.
"""
from __future__ import annotations

import asyncio
import json


def sse_format(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def sse_stream(queue: asyncio.Queue, heartbeat_interval: int = 10):
    """Yield SSE-formatted frames from `queue` until a final event or a
    None sentinel is received, sending a comment-line heartbeat on any
    gap longer than `heartbeat_interval` so idle proxies (Cloud Run) don't
    close the connection."""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"
            continue
        if event is None:
            break
        yield sse_format(event)
        if event.get("final"):
            break


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

    def publish(self, task_id: str, event: dict) -> None:
        """Thread-safe — may be called from the worker thread executing the task."""
        self._loop.call_soon_threadsafe(self._publish_on_loop, task_id, event)

    def _publish_on_loop(self, task_id: str, event: dict) -> None:
        for queue in self._subscribers.get(task_id, []):
            queue.put_nowait(event)
