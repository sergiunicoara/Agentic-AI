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

State changes go through `transition()`, a compare-and-swap on the task's
current state, never through an unconditional `save()`. Without it,
`tasks/cancel` and the executing pipeline race read-modify-write: both
read WORKING, cancel writes CANCELED, then completion overwrites it with
COMPLETED (a lost update that also emits two final events). With CAS,
exactly one of them wins and the loser sees `False`.
"""
from __future__ import annotations

import asyncio
import os
import time
from abc import ABC, abstractmethod
from typing import Iterable

from sentinel.a2a.models import Task, TaskState

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
        """Overwrite an existing task's state and refresh its TTL.

        Unconditional — use `transition()` for state changes that can race."""

    @abstractmethod
    async def transition(self, task_id: str, expected: Iterable[TaskState], new_task: Task) -> bool:
        """Atomically replace the stored task with `new_task` iff it exists and
        its current state is one of `expected`. Returns whether the write
        happened; `False` means another writer changed the state first."""

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

    async def transition(self, task_id: str, expected: Iterable[TaskState], new_task: Task) -> bool:
        expected = frozenset(expected)
        async with self._lock:
            self._purge_expired_locked()
            entry = self._tasks.get(task_id)
            if entry is None or entry[0].status.state not in expected:
                return False
            self._tasks[task_id] = (new_task, time.monotonic())
            return True


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

    # Bounded: each retry only happens when the competing key expired in the
    # few microseconds between our NX SET and GET, so two in a row is already
    # pathological.
    _CREATE_ATTEMPTS = 3

    async def create_if_absent(self, task: Task) -> tuple[Task, bool]:
        for _ in range(self._CREATE_ATTEMPTS):
            created = await self._redis.set(
                self._key(task.id), task.model_dump_json(), nx=True, ex=self.ttl_seconds
            )
            if created:
                return task, True
            existing = await self.get(task.id)
            if existing is not None:
                return existing, False
            # The existing key expired between SET NX and GET. Nothing is
            # stored under this id now, so claiming "created" without writing
            # would hand back a task that doesn't exist — retry the NX write.
        raise RuntimeError(f"could not create or read task {task.id} (key churning under TTL)")

    async def get(self, task_id: str) -> Task | None:
        raw = await self._redis.get(self._key(task_id))
        return Task.model_validate_json(raw) if raw is not None else None

    async def save(self, task: Task) -> None:
        await self._redis.set(self._key(task.id), task.model_dump_json(), ex=self.ttl_seconds)

    async def transition(self, task_id: str, expected: Iterable[TaskState], new_task: Task) -> bool:
        """Optimistic CAS via WATCH/MULTI: if any other client writes the key
        between our read and EXEC, the transaction aborts with WatchError and
        we re-check the state from scratch. (WATCH rather than a Lua script so
        it works the same on fakeredis without the optional `lupa` dependency.)"""
        from redis.exceptions import WatchError

        expected = frozenset(expected)
        key = self._key(task_id)
        payload = new_task.model_dump_json()
        async with self._redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None or Task.model_validate_json(raw).status.state not in expected:
                        await pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.set(key, payload, ex=self.ttl_seconds)
                    await pipe.execute()
                    return True
                except WatchError:
                    continue

    async def close(self) -> None:
        await self._redis.aclose()


def get_task_store() -> TaskStore:
    """Build the task store the process should use, from environment config."""
    ttl_seconds = int(os.environ.get("SENTINEL_TASK_TTL_SECONDS", DEFAULT_TASK_TTL_SECONDS))
    redis_url = os.environ.get("SENTINEL_REDIS_URL")
    if redis_url:
        return RedisTaskStore(redis_url, ttl_seconds=ttl_seconds)
    return InMemoryTaskStore(ttl_seconds=ttl_seconds)
