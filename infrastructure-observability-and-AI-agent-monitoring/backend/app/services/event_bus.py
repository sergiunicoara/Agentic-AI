"""In-process asyncio.Queue-based pub/sub for fanning out agent events
to all connected frontend subscribers."""

import asyncio
import uuid
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings
from app.generated import agent_events_pb2


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._redis = aioredis.from_url(settings.redis_url)
        self._node_id = str(uuid.uuid4())

    def subscribe(self, sub_id: Optional[str] = None) -> tuple[str, asyncio.Queue]:
        sub_id = sub_id or str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subscribers[sub_id] = queue
        self._tasks[sub_id] = asyncio.create_task(self._stream_to_queue(sub_id, queue))
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        self._subscribers.pop(sub_id, None)
        task = self._tasks.pop(sub_id, None)
        if task:
            task.cancel()

    async def _stream_to_queue(self, sub_id: str, queue: asyncio.Queue) -> None:
        cursor = "$"
        try:
            while sub_id in self._subscribers:
                rows = await self._redis.xread({"agent_events": cursor}, block=30_000, count=100)
                for _, entries in rows:
                    for entry_id, fields in entries:
                        cursor = entry_id
                        if fields.get(b"source", fields.get("source", b"")) == self._node_id.encode():
                            continue
                        payload = fields.get(b"payload", fields.get("payload", b""))
                        event = agent_events_pb2.AgentEvent.FromString(payload)
                        self._enqueue(queue, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Redis outages must not crash the gRPC server; local delivery still works.
            return

    @staticmethod
    def _enqueue(queue: asyncio.Queue, event) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            queue.get_nowait()
            queue.put_nowait(event)

    async def publish(self, event) -> None:
        # Deliver locally immediately and append to a shared stream so
        # subscribers connected to another replica receive the same event.
        for queue in list(self._subscribers.values()):
            self._enqueue(queue, event)
        try:
            await self._redis.xadd(
                "agent_events",
                {"payload": event.SerializeToString(), "source": self._node_id},
                maxlen=10_000,
                approximate=True,
            )
        except Exception:
            # Persistence already succeeded; live delivery is best-effort.
            return

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Global singleton shared between FastAPI and gRPC servicer
event_bus = EventBus()
