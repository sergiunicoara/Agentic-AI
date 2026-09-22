"""
Tests for A2A task cancellation: cooperative mid-flight abort (the store
itself is the source of truth a cancel request writes to and the
`on_progress` checkpoint reads from), the terminal-state guard against
canceling an already-finished task, and canceling a submitted-but-not-yet-
working task.
"""
import asyncio
import time

import pytest

from sentinel.a2a import task_service as task_service_module
from sentinel.a2a.jsonrpc import TaskNotCancelableError
from sentinel.a2a.streaming import EventBroadcaster
from sentinel.a2a.task_service import TaskService
from sentinel.a2a.task_store import InMemoryTaskStore
from sentinel.models.schemas import Attestation


def _make_slow_stub(stage_count=6, delay=0.1):
    calls = []

    def stub(target_path, verbose=False, on_progress=None, **kwargs):
        for i in range(stage_count):
            time.sleep(delay)
            if on_progress:
                on_progress({"type": "stage", "stage": f"stage{i}"})
            calls.append(i)
        return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")

    return stub, calls


def test_cancel_mid_flight_stops_execution_and_sticks(monkeypatch):
    stub, calls = _make_slow_stub()
    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster())
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})

        await asyncio.sleep(0.35)  # let a handful of stages run
        canceled = await service.cancel({"id": task.id})
        assert canceled.status.state.value == "canceled"

        calls_at_cancel = len(calls)
        await asyncio.sleep(0.5)  # give the worker thread time to notice and unwind
        assert len(calls) < 6, "stub should never reach its last stage after cancellation"
        assert len(calls) <= calls_at_cancel + 1, "no further stages should complete after cancel()"

        final = await service.get({"id": task.id})
        assert final.status.state.value == "canceled"

    asyncio.run(scenario())


def test_canceling_an_already_terminal_task_raises_not_cancelable(monkeypatch):
    def instant_stub(target_path, verbose=False, on_progress=None, **kwargs):
        return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")

    monkeypatch.setattr(task_service_module, "run_sentinel", instant_stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster())
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = await service.get({"id": task.id})
            if current.status.state.value == "completed":
                break
            await asyncio.sleep(0.05)

        with pytest.raises(TaskNotCancelableError):
            await service.cancel({"id": task.id})

    asyncio.run(scenario())


def test_cancel_before_pipeline_starts_working_is_still_honored(monkeypatch):
    stub, calls = _make_slow_stub()
    monkeypatch.setattr(task_service_module, "run_sentinel", stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster())
        task = await service.send({"metadata": {"target_path": "targets/c1_clean"}})
        # Cancel immediately. Even if _execute's task happens to be scheduled
        # first, the stub's first on_progress checkpoint is still 0.1s away,
        # which is an enormous margin next to asyncio scheduling overhead —
        # the cancel write will land well before that checkpoint fires.
        canceled = await service.cancel({"id": task.id})
        assert canceled.status.state.value == "canceled"

        await asyncio.sleep(0.3)
        assert calls == []  # _execute must have bailed out before ever running the pipeline

        final = await service.get({"id": task.id})
        assert final.status.state.value == "canceled"

    asyncio.run(scenario())
