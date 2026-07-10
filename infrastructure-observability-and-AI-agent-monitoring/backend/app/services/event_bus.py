"""In-process asyncio.Queue-based pub/sub for fanning out agent events
to all connected frontend subscribers."""

import asyncio
import uuid
from typing import Optional


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(self, sub_id: Optional[str] = None) -> tuple[str, asyncio.Queue]:
        sub_id = sub_id or str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subscribers[sub_id] = queue
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        self._subscribers.pop(sub_id, None)

    async def publish(self, event) -> None:
        dead = []
        for sub_id, queue in self._subscribers.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer — drop oldest, push newest
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except Exception:
                    dead.append(sub_id)
        for sub_id in dead:
            self.unsubscribe(sub_id)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Global singleton shared between FastAPI and gRPC servicer
event_bus = EventBus()
