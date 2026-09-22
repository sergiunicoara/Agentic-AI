"""
Tests for the TaskStore abstraction: in-memory TTL/round-trip behavior, and
Redis-backed create-if-absent (idempotency primitive) + restart-survival
(retrieval via a *fresh* store instance, simulating a new process attaching
to the same Redis). Uses fakeredis so this runs hermetically, no live Redis
required.
"""
import asyncio
import time

import fakeredis

from sentinel.a2a.models import Task, TaskState, TaskStatus
from sentinel.a2a.task_store import InMemoryTaskStore, RedisTaskStore


def _task(task_id: str, state: TaskState = TaskState.SUBMITTED) -> Task:
    return Task(id=task_id, status=TaskStatus(state=state))


def test_in_memory_create_if_absent_is_idempotent():
    async def scenario():
        store = InMemoryTaskStore(ttl_seconds=3600)
        first, created1 = await store.create_if_absent(_task("t1"))
        second, created2 = await store.create_if_absent(_task("t1", TaskState.WORKING))
        assert created1 is True
        assert created2 is False
        assert second.status.state == TaskState.SUBMITTED  # unchanged — the original wins

    asyncio.run(scenario())


def test_in_memory_save_overwrites_and_get_reflects_it():
    async def scenario():
        store = InMemoryTaskStore(ttl_seconds=3600)
        await store.create_if_absent(_task("t1"))
        await store.save(_task("t1", TaskState.COMPLETED))
        fetched = await store.get("t1")
        assert fetched.status.state == TaskState.COMPLETED

    asyncio.run(scenario())


def test_in_memory_ttl_expires_stale_tasks():
    async def scenario():
        store = InMemoryTaskStore(ttl_seconds=0.1)
        await store.create_if_absent(_task("stale"))
        time.sleep(0.2)
        assert await store.get("stale") is None

    asyncio.run(scenario())


def test_in_memory_get_missing_task_returns_none():
    async def scenario():
        store = InMemoryTaskStore()
        assert await store.get("nope") is None

    asyncio.run(scenario())


def _fake_redis_store() -> RedisTaskStore:
    server = fakeredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    return RedisTaskStore(client=client, ttl_seconds=3600), server


def test_redis_store_create_if_absent_is_atomic_idempotency_primitive():
    async def scenario():
        store, _server = _fake_redis_store()
        first, created1 = await store.create_if_absent(_task("t1"))
        second, created2 = await store.create_if_absent(_task("t1", TaskState.WORKING))
        assert created1 is True
        assert created2 is False
        assert second.status.state == TaskState.SUBMITTED

    asyncio.run(scenario())


def test_redis_store_survives_a_fresh_instance_reattaching():
    """Simulates an app restart: a *new* RedisTaskStore instance (fresh
    Python object, same backing Redis) can still retrieve the task."""
    async def scenario():
        server = fakeredis.FakeServer()
        client_a = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
        store_a = RedisTaskStore(client=client_a, ttl_seconds=3600)
        await store_a.create_if_absent(_task("t1"))
        await store_a.save(_task("t1", TaskState.COMPLETED))

        client_b = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
        store_b = RedisTaskStore(client=client_b, ttl_seconds=3600)
        fetched = await store_b.get("t1")
        assert fetched is not None
        assert fetched.status.state == TaskState.COMPLETED

    asyncio.run(scenario())
