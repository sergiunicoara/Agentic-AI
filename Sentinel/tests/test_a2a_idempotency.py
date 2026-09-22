"""
Tests for idempotency: the task id doubles as the idempotency key (the
natural A2A semantics — `create_if_absent` in the task store is the atomic
primitive this relies on). A repeated `message/send` with the same id must
not launch the pipeline twice.
"""
import asyncio

from sentinel.a2a import task_service as task_service_module
from sentinel.a2a.streaming import EventBroadcaster
from sentinel.a2a.task_service import TaskService
from sentinel.a2a.task_store import InMemoryTaskStore
from sentinel.models.schemas import Attestation


def test_same_task_id_sent_twice_runs_pipeline_once(monkeypatch):
    calls = []

    def counting_stub(target_path, verbose=False, on_progress=None, **kwargs):
        calls.append(target_path)
        return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")

    monkeypatch.setattr(task_service_module, "run_sentinel", counting_stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster())
        params = {"id": "fixed-task", "metadata": {"target_path": "targets/c1_clean"}}

        first = await service.send(params)
        second = await service.send(params)

        assert first.id == second.id == "fixed-task"
        assert "idempotentReplay" not in first.metadata
        assert second.metadata.get("idempotentReplay") is True

        await asyncio.sleep(0.2)  # let the single scheduled execution finish
        assert len(calls) == 1

    asyncio.run(scenario())


def test_different_task_ids_each_run_the_pipeline(monkeypatch):
    calls = []

    def counting_stub(target_path, verbose=False, on_progress=None, **kwargs):
        calls.append(target_path)
        return Attestation(target=target_path, verdict="pass", findings=[], signature="sig", audit_ref="ref")

    monkeypatch.setattr(task_service_module, "run_sentinel", counting_stub)

    async def scenario():
        service = TaskService(InMemoryTaskStore(), EventBroadcaster())
        await service.send({"id": "task-a", "metadata": {"target_path": "targets/c1_clean"}})
        await service.send({"id": "task-b", "metadata": {"target_path": "targets/c1_clean"}})
        await asyncio.sleep(0.2)
        assert len(calls) == 2

    asyncio.run(scenario())
