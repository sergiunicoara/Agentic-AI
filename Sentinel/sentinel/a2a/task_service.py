"""
A2A task orchestration: framework-agnostic (no FastAPI imports) so the
protocol wiring in server.py stays a thin adapter over this module.

Concurrency model: `send`/`get`/`cancel` all run on the FastAPI event
loop. Actually executing a task (`_execute`) also runs as a coroutine on
that same loop, but the blocking Sentinel pipeline call itself is pushed
into a worker thread via `run_in_executor` — mirroring the pattern the
`/ws/scan` WebSocket already uses so long-running subprocess calls
(bandit, semgrep, pip-audit) never block the event loop.

Cancellation is store-centric, not a separate in-memory flag: the
`on_progress` callback (invoked from the worker thread between pipeline
stages) reads the task's *current* state back from the TaskStore before
each stage. This makes a `tasks/cancel` call correct even when it lands
on a different process than the one executing the task (Redis-backed,
multi-instance deployment) — whichever instance is running the pipeline
will see the canceled state on its next checkpoint and stop.
"""
from __future__ import annotations

import asyncio
import logging

from sentinel.a2a.jsonrpc import (
    InvalidParamsError,
    TaskNotCancelableError,
    TaskNotFoundError,
)
from sentinel.a2a.models import (
    Artifact,
    Message,
    Part,
    Task,
    TaskState,
    TaskStatus,
    new_task_id,
    now_iso,
)
from sentinel.a2a.streaming import EventBroadcaster
from sentinel.a2a.task_store import TaskStore
from sentinel.a2a.telemetry import tracer
from sentinel.pipeline import run_sentinel

logger = logging.getLogger("sentinel.a2a")


class _TaskCanceled(Exception):
    """Raised from within on_progress to unwind out of run_sentinel cooperatively."""


def _extract_task_id(params: dict) -> str | None:
    if params.get("id"):
        return params["id"]
    message = params.get("message") or {}
    if message.get("taskId"):
        return message["taskId"]
    metadata = params.get("metadata") or {}
    return metadata.get("task_id")


def _extract_target_path(params: dict) -> str:
    metadata = params.get("metadata") or {}
    if metadata.get("target_path"):
        return metadata["target_path"]
    message = params.get("message") or {}
    for part in message.get("parts", []):
        if part.get("kind", "text") == "text" and part.get("text"):
            return part["text"]
    raise InvalidParamsError("params.message must include a text part, or set params.metadata.target_path")


def _status_event(task: Task, final: bool, extra: dict | None = None) -> dict:
    event = {
        "taskId": task.id,
        "status": {"state": task.status.state.value, "timestamp": task.status.timestamp},
        "final": final,
    }
    if extra:
        event.update(extra)
    return event


def _error_message(text: str) -> Message:
    return Message(role="agent", parts=[Part(kind="text", text=text)])


def _attestation_to_result(attestation, red_team_result) -> dict:
    return {
        "verdict": attestation.verdict,
        "findings_count": len(attestation.findings),
        "findings": [
            {
                "title": f.title,
                "severity": f.severity,
                "pillar": f.pillar,
                "evidence_ids": f.evidence_ids,
                "remediation": f.remediation,
            }
            for f in attestation.findings
        ],
        "audit_ref": attestation.audit_ref,
        "signature": attestation.signature,
        "red_team": red_team_result,
    }


class TaskService:
    def __init__(self, store: TaskStore, broadcaster: EventBroadcaster):
        self.store = store
        self.broadcaster = broadcaster

    async def send(self, params: dict) -> Task:
        with tracer.start_as_current_span("a2a.tasks.send"):
            task, created = await self._create_or_replay(params)
            if created:
                asyncio.create_task(self._execute(task.id))
            return task

    async def send_stream(self, params: dict) -> tuple[Task, asyncio.Queue]:
        with tracer.start_as_current_span("a2a.tasks.send_stream"):
            task, created = await self._create_or_replay(params)
            queue = self._subscribe_queue(task)
            if created:
                asyncio.create_task(self._execute(task.id))
            return task, queue

    async def get(self, params: dict) -> Task:
        with tracer.start_as_current_span("a2a.tasks.get"):
            task_id = params.get("id")
            if not task_id:
                raise InvalidParamsError("params.id is required")
            task = await self.store.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"No task with id {task_id}")
            history_length = params.get("historyLength")
            if isinstance(history_length, int):
                task = task.model_copy(update={"history": task.history[-history_length:]})
            return task

    async def cancel(self, params: dict) -> Task:
        with tracer.start_as_current_span("a2a.tasks.cancel"):
            task_id = params.get("id")
            if not task_id:
                raise InvalidParamsError("params.id is required")
            task = await self.store.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"No task with id {task_id}")
            if task.status.state.is_terminal:
                raise TaskNotCancelableError(f"Task {task_id} is already {task.status.state.value}")
            canceled = task.with_status(TaskState.CANCELED)
            await self.store.save(canceled)
            logger.info("a2a.task.canceled task_id=%s", task_id)
            self.broadcaster.publish(task_id, _status_event(canceled, final=True))
            return canceled

    async def resubscribe(self, params: dict) -> asyncio.Queue:
        with tracer.start_as_current_span("a2a.tasks.resubscribe"):
            task_id = params.get("id")
            if not task_id:
                raise InvalidParamsError("params.id is required")
            task = await self.store.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"No task with id {task_id}")
            return self._subscribe_queue(task)

    def _subscribe_queue(self, task: Task) -> asyncio.Queue:
        if task.status.state.is_terminal:
            queue: asyncio.Queue = asyncio.Queue()
            queue.put_nowait(_status_event(task, final=True))
            return queue
        queue = self.broadcaster.subscribe(task.id)
        queue.put_nowait(_status_event(task, final=False))
        return queue

    async def _create_or_replay(self, params: dict) -> tuple[Task, bool]:
        target_path = _extract_target_path(params)
        metadata_in = params.get("metadata") or {}
        task_id = _extract_task_id(params) or new_task_id()

        message = Message(
            role="user",
            taskId=task_id,
            parts=[Part(kind="text", text=target_path)],
            metadata=metadata_in or None,
        )
        task = Task(
            id=task_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            history=[message],
            metadata={
                "target_path": target_path,
                "include_red_team": bool(metadata_in.get("include_red_team", False)),
                "include_llm_auditor": bool(metadata_in.get("include_llm_auditor", False)),
                "created_at": now_iso(),
            },
        )
        stored, created = await self.store.create_if_absent(task)
        if created:
            logger.info("a2a.task.submitted task_id=%s target=%s", task_id, target_path)
        else:
            stored = stored.model_copy(update={"metadata": {**stored.metadata, "idempotentReplay": True}})
            logger.info("a2a.task.idempotent_replay task_id=%s", task_id)
        return stored, created

    async def _execute(self, task_id: str) -> None:
        with tracer.start_as_current_span("a2a.tasks.execute"):
            await self._execute_body(task_id)

    async def _execute_body(self, task_id: str) -> None:
        loop = asyncio.get_running_loop()
        task = await self.store.get(task_id)
        if task is None or task.status.state.is_terminal:
            return

        task = task.with_status(TaskState.WORKING)
        await self.store.save(task)
        logger.info("a2a.task.working task_id=%s", task_id)
        self.broadcaster.publish(task_id, _status_event(task, final=False))

        metadata = task.metadata

        def on_progress(event: dict) -> None:
            current = asyncio.run_coroutine_threadsafe(self.store.get(task_id), loop).result()
            if current is not None and current.status.state == TaskState.CANCELED:
                raise _TaskCanceled()
            self.broadcaster.publish(
                task_id, {"taskId": task_id, "kind": "progress", "data": event, "final": False}
            )

        def run_pipeline():
            if metadata.get("include_red_team"):
                return run_sentinel(
                    metadata["target_path"],
                    verbose=False,
                    include_red_team=True,
                    return_red_team=True,
                    include_llm_auditor=metadata.get("include_llm_auditor", False),
                    on_progress=on_progress,
                )
            attestation = run_sentinel(
                metadata["target_path"],
                verbose=False,
                include_llm_auditor=metadata.get("include_llm_auditor", False),
                on_progress=on_progress,
            )
            return attestation, None

        try:
            attestation, red_team_result = await loop.run_in_executor(None, run_pipeline)
        except _TaskCanceled:
            logger.info("a2a.task.canceled_during_execution task_id=%s", task_id)
            return
        except Exception as exc:  # noqa: BLE001 - pipeline failures become a task-level failure, not a crash
            logger.exception("a2a.task.failed task_id=%s", task_id)
            current = await self.store.get(task_id)
            if current is None or current.status.state == TaskState.CANCELED:
                return
            failed = current.with_status(TaskState.FAILED, message=_error_message(str(exc)))
            await self.store.save(failed)
            self.broadcaster.publish(task_id, _status_event(failed, final=True))
            return

        current = await self.store.get(task_id)
        if current is None or current.status.state == TaskState.CANCELED:
            return
        result = _attestation_to_result(attestation, red_team_result)
        artifact = Artifact(name="attestation", parts=[Part(kind="data", data=result)])
        completed = current.model_copy(update={"artifacts": [artifact]}).with_status(TaskState.COMPLETED)
        await self.store.save(completed)
        logger.info("a2a.task.completed task_id=%s verdict=%s", task_id, attestation.verdict)
        self.broadcaster.publish(task_id, _status_event(completed, final=True))
