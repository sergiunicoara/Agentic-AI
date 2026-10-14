"""
Tests for compare-and-swap task state transitions and the races they close:
store-level CAS semantics on both stores (including a WATCH abort on
Redis and the SET NX / GET expiry race), and service-level cancel vs.
complete — a canceled task stays canceled and exactly one final event is
published. Also covers admission control (bounded concurrent pipelines),
the non-blocking cancel checkpoint, and that an "inconclusive" verdict is
an ordinary completed result.
"""
import asyncio
import threading
import time

import fakeredis
import pytest

from sentinel.a2a import task_service as task_service_module
from sentinel.a2a.jsonrpc import TaskNotCancelableError
from sentinel.a2a.models import Task, TaskState, TaskStatus
from sentinel.a2a.streaming import EventBroadcaster
from sentinel.a2a.task_service import TaskService
from sentinel.a2a.task_store import InMemoryTaskStore, RedisTaskStore
from sentinel.models.schemas import Attestation


def _task(task_id: str, state: TaskState = TaskState.SUBMITTED) -> Task:
    return Task(id=task_id, status=TaskStatus(state=state))


def _redis_pair():
    server = fakeredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    return RedisTaskStore(client=client, ttl_seconds=3600), server


def _make_store(kind: str):
    if kind == "memory":
        return InMemoryTaskStore(ttl_seconds=3600)
    return _redis_pair()[0]


STORES = ["memory", "redis"]


def _attestation(target_path, verdict="pass", **extra):
    return Attestation(target=target_path, verdict=verdict, findings=[], signature="sig", audit_ref="ref", **extra)


async def _wait_idle(service: TaskService, timeout: float = 10) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while service._background and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert not service._background, "background execution should have finished"


def _spy_on_publish(broadcaster: EventBroadcaster) -> list[dict]:
    published = []
    real_publish = broadcaster.publish

    def spy(task_id, event):
        published.append(event)
        real_publish(task_id, event)

    broadcaster.publish = spy
    return published


# ---- store-level CAS ----------------------------------------------------------

@pytest.mark.parametrize("store_kind", STORES)
def test_transition_writes_only_from_expected_state(store_kind):
    async def scenario():
        store = _make_store(store_kind)
        await store.create_if_absent(_task("t1"))
        assert await store.transition("t1", {TaskState.SUBMITTED}, _task("t1", TaskState.WORKING)) is True
        assert (await store.get("t1")).status.state == TaskState.WORKING
        assert await store.transition("t1", {TaskState.SUBMITTED}, _task("t1", TaskState.FAILED)) is False
        assert (await store.get("t1")).status.state == TaskState.WORKING

    asyncio.run(scenario())


@pytest.mark.parametrize("store_kind", STORES)
def test_transition_on_missing_task_is_refused_and_creates_nothing(store_kind):
    async def scenario():
        store = _make_store(store_kind)
        assert await store.transition("ghost", {TaskState.WORKING}, _task("ghost", TaskState.COMPLETED)) is False
        assert await store.get("ghost") is None

    asyncio.run(scenario())


@pytest.mark.parametrize("store_kind", STORES)
def test_stale_completion_cannot_overwrite_a_cancel(store_kind):
    """The lost-update interleaving: completion read WORKING, cancel then
    wrote CANCELED; completion's write must now be refused."""
    async def scenario():
        store = _make_store(store_kind)
        await store.create_if_absent(_task("t1", TaskState.WORKING))
        stale = await store.get("t1")
        assert await store.transition(
            "t1", {TaskState.SUBMITTED, TaskState.WORKING}, stale.with_status(TaskState.CANCELED)
        )
        assert await store.transition("t1", {TaskState.WORKING}, stale.with_status(TaskState.COMPLETED)) is False
        assert (await store.get("t1")).status.state == TaskState.CANCELED

    asyncio.run(scenario())


def test_redis_transition_rechecks_state_when_key_changes_under_watch():
    """Another client writes between WATCH/GET and EXEC: the transaction
    aborts and the retry must decide against the new state."""
    async def scenario():
        store, server = _redis_pair()
        other = RedisTaskStore(
            client=fakeredis.aioredis.FakeRedis(server=server, decode_responses=True), ttl_seconds=3600
        )
        await store.create_if_absent(_task("t1", TaskState.WORKING))

        real_pipeline = store._redis.pipeline
        interfered = False

        def pipeline_with_interference(*args, **kwargs):
            pipe = real_pipeline(*args, **kwargs)
            real_get = pipe.get

            async def get_then_interfere(key):
                nonlocal interfered
                value = await real_get(key)
                if not interfered:
                    interfered = True
                    await other.save(_task("t1", TaskState.CANCELED))
                return value

            pipe.get = get_then_interfere
            return pipe

        store._redis.pipeline = pipeline_with_interference
        won = await store.transition("t1", {TaskState.WORKING}, _task("t1", TaskState.COMPLETED))
        assert interfered
        assert won is False
        assert (await store.get("t1")).status.state == TaskState.CANCELED

    asyncio.run(scenario())


def test_redis_create_if_absent_retries_when_existing_key_expires_mid_check():
    """SET NX loses (key exists), then the key expires before GET: the store
    must retry the NX write, not report created=True with nothing stored."""
    async def scenario():
        store, _server = _redis_pair()
        real_set = store._redis.set
        calls = []

        async def set_losing_first_race(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return None  # as if another task held the key at this instant
            return await real_set(*args, **kwargs)

        store._redis.set = set_losing_first_race
        stored, created = await store.create_if_absent(_task("t1"))
        assert created is True
        assert stored.id == "t1"
        assert len(calls) == 2
        assert await store.get("t1") is not None

    asyncio.run(scenario())


# ---- service-level races ---------------------------------------------------------

@pytest.mark.parametrize("store_kind", STORES)
def test_cancel_landing_after_last_checkpoint_wins_over_completion(monkeypatch, store_kind):
    """The pipeline passes its last cancel checkpoint, then a cancel lands
    while it is finishing. Completion must lose the CAS: the task stays
    canceled and exactly one final event (canceled) is published."""
    holder = {}

    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        on_progress({"type": "stage", "stage": "last"})
        asyncio.run_coroutine_threadsafe(
            holder["service"].cancel({"id": "race-task"}), holder["loop"]
        ).result(timeout=5)
        return _attestation(target_path)

    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    async def scenario():
        broadcaster = EventBroadcaster()
        published = _spy_on_publish(broadcaster)
        service = TaskService(_make_store(store_kind), broadcaster)
        holder.update(service=service, loop=asyncio.get_running_loop())

        await service.send({"id": "race-task", "metadata": {"target_path": "targets/c1_clean"}})
        await _wait_idle(service)

        final = await service.get({"id": "race-task"})
        assert final.status.state.value == "canceled"
        assert final.artifacts == []
        finals = [e for e in published if e.get("final")]
        assert len(finals) == 1
        assert finals[0]["status"]["state"] == "canceled"
        assert not any(e.get("kind") == "artifact-update" for e in published)

    asyncio.run(scenario())


@pytest.mark.parametrize("store_kind", STORES)
def test_concurrent_cancels_succeed_once_and_publish_one_final_event(monkeypatch, store_kind):
    def slow_stub(target_path, verbose=False, on_progress=None, **kwargs):
        for i in range(40):
            time.sleep(0.02)
            on_progress({"type": "stage", "stage": f"s{i}"})
        return _attestation(target_path)

    monkeypatch.setattr(task_service_module, "run_sentinel", slow_stub)

    async def scenario():
        broadcaster = EventBroadcaster()
        published = _spy_on_publish(broadcaster)
        service = TaskService(_make_store(store_kind), broadcaster)
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})
        await asyncio.sleep(0.1)
        results = await asyncio.gather(
            *(service.cancel({"id": task.id}) for _ in range(5)), return_exceptions=True
        )
        assert sum(1 for r in results if not isinstance(r, Exception)) == 1
        assert all(isinstance(r, TaskNotCancelableError) for r in results if isinstance(r, Exception))
        await _wait_idle(service)
        assert sum(1 for e in published if e.get("final")) == 1
        assert (await service.get({"id": task.id})).status.state.value == "canceled"

    asyncio.run(scenario())


def test_cancel_check_times_out_instead_of_hanging(monkeypatch):
    """If the loop can't answer the worker thread's cancel check in time,
    the checkpoint is skipped and the pipeline keeps going (no deadlock)."""
    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        for i in range(3):
            on_progress({"type": "stage", "stage": f"s{i}"})
        return _attestation(target_path)

    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    class SlowReadsStore(InMemoryTaskStore):
        slow = False

        async def get(self, task_id):
            if self.slow:
                await asyncio.sleep(1)
            return await super().get(task_id)

        async def transition(self, task_id, expected, new_task):
            won = await super().transition(task_id, expected, new_task)
            if won and new_task.status.state == TaskState.WORKING:
                self.slow = True  # only the in-flight cancel checks are slow
            return won

    async def scenario():
        store = SlowReadsStore()
        service = TaskService(store, EventBroadcaster(), progress_check_timeout=0.05)
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})
        started = time.monotonic()
        await _wait_idle(service)
        store.slow = False
        assert time.monotonic() - started < 3, "three 1s reads would mean the checks blocked"
        assert (await service.get({"id": task.id})).status.state.value == "completed"

    asyncio.run(scenario())


def test_admission_semaphore_bounds_concurrent_pipelines(monkeypatch):
    lock = threading.Lock()
    running = {"now": 0, "peak": 0}

    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        with lock:
            running["now"] += 1
            running["peak"] = max(running["peak"], running["now"])
        time.sleep(0.1)
        with lock:
            running["now"] -= 1
        return _attestation(target_path)

    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster(), max_concurrent_scans=2)
        tasks = [await service.send({"metadata": {"target_path": "targets/c1_clean"}}) for _ in range(5)]
        await _wait_idle(service)
        states = [(await service.get({"id": t.id})).status.state.value for t in tasks]
        assert states == ["completed"] * 5
        assert running["peak"] == 2

    asyncio.run(scenario())


def test_task_waiting_for_admission_can_be_canceled_and_never_runs(monkeypatch):
    release = threading.Event()
    ran = []

    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        ran.append(target_path)
        release.wait(timeout=5)
        return _attestation(target_path)

    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster(), max_concurrent_scans=1)
        await service.send({"metadata": {"target_path": "first"}})
        queued = await service.send({"metadata": {"target_path": "second"}})
        await asyncio.sleep(0.1)
        assert (await service.get({"id": queued.id})).status.state.value == "submitted"
        await service.cancel({"id": queued.id})
        release.set()
        await _wait_idle(service)
        assert ran == ["first"]
        assert (await service.get({"id": queued.id})).status.state.value == "canceled"

    try:
        asyncio.run(scenario())
    finally:
        release.set()


def test_inconclusive_verdict_is_a_normal_completed_result(monkeypatch):
    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        return _attestation(target_path, verdict="inconclusive", inconclusive_reasons=["semgrep: executable not found"])

    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster())
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})
        await _wait_idle(service)
        final = await service.get({"id": task.id})
        assert final.status.state.value == "completed"
        result = final.artifacts[0].parts[0].data
        assert result["verdict"] == "inconclusive"
        assert result["inconclusive_reasons"] == ["semgrep: executable not found"]

    asyncio.run(scenario())
