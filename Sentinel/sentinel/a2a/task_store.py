"""
Durable storage abstraction for A2A tasks.

Two implementations:
  - InMemoryTaskStore: dict-backed, TTL measured from last write, lazy
    eviction sweep on write (generalizes the previous module-level
    `tasks` dict + `_evict_stale_tasks()` in server.py). Used whenever
    SENTINEL_REDIS_URL is not set — local dev and the test suite.
  - RedisTaskStore: `redis.asyncio`-backed so task state survives
    process restarts and is visible across multiple instances (e.g.
    several Cloud Run replicas behind one load balancer). Uses
    `SET NX` for atomic create-if-absent, which is also the primitive
    idempotency relies on: two concurrent submissions with the same
    task id race on the same NX write, and only one can "win" creation.

Both stores refresh the TTL on every write so an in-progress task
never expires out from under itself, and let it expire TASK_TTL_SECONDS
after the last touch (matching the previous eviction behavior).
"""
from __future__ import annotations

import asyncio
import os
import time
from abc import ABC, abstractmethod

from sentinel.a2a.models import Task

DEFAULT_TASK_TTL_SECONDS = 3600


class TaskStore(ABC):
    @abstractmethod
    async def create_if_absent(self, task: Task) -> tuple[Task, bool]:
        """Store `task` if its id isn't already present.

        Returns (stored_task, created) — `stored_task` is `task` itself when
        newly created, or the pre-existing task when one already existed
        (the idempotent-replay case).
        """

    @abstractmethod
    async def get(self, task_id: str) -> Task | None:
        ...

    @abstractmethod
    async def save(self, task: Task) -> None:
        """Overwrite an existing task's state and refresh its TTL."""

    async def close(self) -> None:
        return None


class InMemoryTaskStore(TaskStore):
    def __init__(self, ttl_seconds: int = DEFAULT_TASK_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._tasks: dict[str, tuple[Task, float]] = {}
        self._lock = asyncio.Lock()

    def _purge_expired_locked(self) -> None:
        cutoff = time.monotonic() - self.ttl_seconds
        stale = [tid for tid, (_, touched_at) in self._tasks.items() if touched_at < cutoff]
        for tid in stale:
            del self._tasks[tid]

    async def create_if_absent(self, task: Task) -> tuple[Task, bool]:
        async with self._lock:
            self._purge_expired_locked()
            existing = self._tasks.get(task.id)
            if existing is not None:
                return existing[0], False
            self._tasks[task.id] = (task, time.monotonic())
            return task, True

    async def get(self, task_id: str) -> Task | None:
        async with self._lock:
            self._purge_expired_locked()
            entry = self._tasks.get(task_id)
            return entry[0] if entry else None

    async def save(self, task: Task) -> None:
        async with self._lock:
            self._tasks[task.id] = (task, time.monotonic())


class RedisTaskStore(TaskStore):
    KEY_PREFIX = "sentinel:a2a:task:"

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int = DEFAULT_TASK_TTL_SECONDS,
        client=None,
    ):
        """`client` is an injectable seam for tests (e.g. fakeredis.FakeAsyncRedis) —
        production callers pass `redis_url` and let this build a real client."""
        self.ttl_seconds = ttl_seconds
        if client is not None:
            self._redis = client
        else:
            import redis.asyncio as redis

            self._redis = redis.from_url(redis_url, decode_responses=True)

    def _key(self, task_id: str) -> str:
        return f"{self.KEY_PREFIX}{task_id}"

    async def create_if_absent(self, task: Task) -> tuple[Task, bool]:
        created = await self._redis.set(
            self._key(task.id), task.model_dump_json(), nx=True, ex=self.ttl_seconds
        )
        if created:
            return task, True
        existing = await self.get(task.id)
        return (existing, False) if existing is not None else (task, True)

    async def get(self, task_id: str) -> Task | None:
        raw = await self._redis.get(self._key(task_id))
        return Task.model_validate_json(raw) if raw is not None else None

    async def save(self, task: Task) -> None:
        await self._redis.set(self._key(task.id), task.model_dump_json(), ex=self.ttl_seconds)

    async def close(self) -> None:
        await self._redis.aclose()


def get_task_store() -> TaskStore:
    """Build the task store the process should use, from environment config."""
    ttl_seconds = int(os.environ.get("SENTINEL_TASK_TTL_SECONDS", DEFAULT_TASK_TTL_SECONDS))
    redis_url = os.environ.get("SENTINEL_REDIS_URL")
    if redis_url:
        return RedisTaskStore(redis_url, ttl_seconds=ttl_seconds)
    return InMemoryTaskStore(ttl_seconds=ttl_seconds)
