"""
A2A task orchestration: framework-agnostic (no FastAPI imports) so the
protocol wiring in server.py stays a thin adapter over this module. Both
the JSON-RPC methods and the dashboard's `/ws/scan` WebSocket run scans
through here, so admission control, limits and cancel semantics are
shared rather than duplicated.

Concurrency model: `send`/`get`/`cancel` all run on the FastAPI event
loop. Executing a task (`_execute`) also runs as a coroutine on that same
loop, but the blocking Sentinel pipeline call itself is pushed into a
worker thread so long-running subprocess calls (bandit, semgrep,
pip-audit) never block the event loop. Two bounds apply:
  - an admission semaphore caps how many pipelines run at once (excess
    tasks wait in SUBMITTED, still cancelable);
  - a dedicated ThreadPoolExecutor of the same size runs them, so scans
    never compete with (or starve) the loop's default executor, which
    other code — including `run_coroutine_threadsafe` plumbing in
    libraries — may rely on.
A per-process cap on active (non-terminal) tasks bounds the queue in
front of the semaphore.

Cancellation is store-centric, not a separate in-memory flag: the
`on_progress` callback (invoked from the worker thread between pipeline
stages) reads the task's *current* state back from the TaskStore before
each stage. This makes a `tasks/cancel` call effective even when it lands
on a different process than the one executing the task (Redis-backed,
multi-instance deployment). That check is advisory — it only saves
work. Correctness comes from `TaskStore.transition()`: every state change
is a compare-and-swap, so a cancel and a completion racing each other
can't both win, and only the winner publishes a final event.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import uuid
from typing import Any, AsyncIterator

from sentinel.a2a import limits
from sentinel.a2a.jsonrpc import (
    InvalidParamsError,
    ServerBusyError,
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
from sentinel.a2a.streaming import HEARTBEAT, EventBroadcaster, EventStream
from sentinel.a2a.task_store import TaskStore
from sentinel.a2a.telemetry import tracer
from sentinel.pipeline import run_sentinel

logger = logging.getLogger("sentinel.a2a")

_CANCELABLE = frozenset({TaskState.SUBMITTED, TaskState.WORKING})
_MAX_TASK_ID_LENGTH = 128


class _TaskCanceled(Exception):
    """Raised from within on_progress to unwind out of run_sentinel cooperatively."""


def new_context_id() -> str:
    return f"ctx_{uuid.uuid4().hex[:12]}"


def _require_id(params: dict) -> str:
    task_id = params.get("id")
    if not task_id:
        raise InvalidParamsError("params.id is required")
    if not isinstance(task_id, str):
        raise InvalidParamsError("params.id must be a string")
    return task_id


def _as_object(params: dict, key: str) -> dict:
    value = params.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidParamsError(f"params.{key} must be an object")
    return value


def _extract_task_id(params: dict) -> str | None:
    message = _as_object(params, "message")
    metadata = _as_object(params, "metadata")
    task_id = params.get("id") or message.get("taskId") or metadata.get("task_id")
    if task_id is None:
        return None
    if not isinstance(task_id, str) or not task_id or len(task_id) > _MAX_TASK_ID_LENGTH:
        raise InvalidParamsError(f"task id must be a non-empty string of at most {_MAX_TASK_ID_LENGTH} characters")
    return task_id


def _extract_target_path(params: dict) -> str:
    metadata = _as_object(params, "metadata")
    if metadata.get("target_path"):
        if not isinstance(metadata["target_path"], str):
            raise InvalidParamsError("params.metadata.target_path must be a string")
        return metadata["target_path"]
    message = _as_object(params, "message")
    parts = message.get("parts") or []
    if not isinstance(parts, list):
        raise InvalidParamsError("params.message.parts must be an array")
    for part in parts:
        if isinstance(part, dict) and part.get("kind", "text") == "text" and isinstance(part.get("text"), str) and part["text"]:
            return part["text"]
    raise InvalidParamsError("params.message must include a text part, or set params.metadata.target_path")


def _extract_context_id(params: dict) -> str:
    """Echo the caller's contextId when given (A2A groups related tasks by
    it), otherwise mint one — every Task and event must carry one."""
    context_id = _as_object(params, "message").get("contextId")
    if isinstance(context_id, str) and context_id and len(context_id) <= _MAX_TASK_ID_LENGTH:
        return context_id
    return new_context_id()


def _status_event(task: Task, final: bool, message: Message | None = None) -> dict:
    """A2A TaskStatusUpdateEvent. With `message`, a fresh status is built so
    progress updates carry their own timestamp rather than the transition's."""
    status = task.status if message is None else TaskStatus(state=task.status.state, message=message)
    return {
        "kind": "status-update",
        "taskId": task.id,
        "contextId": task.contextId,
        "status": status.model_dump(mode="json", exclude_none=True),
        "final": final,
    }


def _progress_event(task: Task, data: Any) -> dict:
    """Pipeline progress, carried the spec way: a non-final `working` status
    update whose status.message is an agent message with a data part."""
    payload = data if isinstance(data, dict) else {"value": data}
    message = Message(
        role="agent", taskId=task.id, contextId=task.contextId, parts=[Part(kind="data", data=payload)]
    )
    return _status_event(task, final=False, message=message)


def _artifact_event(task: Task, artifact: Artifact) -> dict:
    """A2A TaskArtifactUpdateEvent — the whole artifact in one chunk."""
    return {
        "kind": "artifact-update",
        "taskId": task.id,
        "contextId": task.contextId,
        "artifact": artifact.model_dump(mode="json", exclude_none=True),
        "append": False,
        "lastChunk": True,
    }


def _terminal_events(task: Task) -> list[dict]:
    """Events a stream emits itself when it learns of a terminal state from
    the store rather than from the broadcaster (cross-instance execution)."""
    events = []
    if task.status.state == TaskState.COMPLETED:
        events.extend(_artifact_event(task, artifact) for artifact in task.artifacts)
    events.append(_status_event(task, final=True))
    return events


def _error_message(text: str) -> Message:
    return Message(role="agent", parts=[Part(kind="text", text=text)])


def _attestation_to_result(attestation, red_team_result) -> dict:
    # Any verdict — including "inconclusive" (a scanner was missing or
    # failed) — is a completed task: the verdict itself is the answer.
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
        "inconclusive_reasons": list(getattr(attestation, "inconclusive_reasons", None) or []),
        "audit_ref": attestation.audit_ref,
        "signature": attestation.signature,
        "red_team": red_team_result,
    }


class TaskService:
    def __init__(
        self,
        store: TaskStore,
        broadcaster: EventBroadcaster,
        *,
        max_concurrent_scans: int | None = None,
        max_active_tasks: int | None = None,
        stream_max_seconds: float | None = None,
        heartbeat_interval: float = 10.0,
        progress_check_timeout: float = 5.0,
    ):
        self.store = store
        self.broadcaster = broadcaster
        concurrency = max_concurrent_scans or limits.max_concurrent_scans()
        self._admission = asyncio.Semaphore(concurrency)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrency, thread_name_prefix="sentinel-scan"
        )
        self.max_active_tasks = max_active_tasks or limits.max_active_tasks()
        self.stream_max_seconds = stream_max_seconds or limits.stream_max_seconds()
        self.heartbeat_interval = heartbeat_interval
        self.progress_check_timeout = progress_check_timeout
        # Ids of tasks this process accepted and hasn't seen reach a terminal
        # state; the per-process active-task cap counts these.
        self._active: set[str] = set()
        self._create_lock = asyncio.Lock()
        # Strong references to fire-and-forget tasks: the event loop only
        # keeps weak ones, so an unreferenced task can be garbage-collected
        # mid-execution.
        self._background: set[asyncio.Task] = set()

    # ---- JSON-RPC methods -------------------------------------------------

    async def send(self, params: dict) -> Task:
        with tracer.start_as_current_span("a2a.tasks.send"):
            task, created = await self._create_or_replay(params)
            if created:
                self._spawn(self._execute(task.id))
            return task

    async def send_stream(self, params: dict) -> tuple[Task, EventStream]:
        with tracer.start_as_current_span("a2a.tasks.send_stream"):
            task, created = await self._create_or_replay(params)
            # Subscribe before execution is scheduled so the stream sees the
            # task's whole lifecycle; a new task's snapshot is the one just
            # created. A replayed task may have moved on since
            # create_if_absent read it, so its stream re-reads the store.
            stream = self.open_stream(task.id, snapshot=task if created else None)
            if created:
                self._spawn(self._execute(task.id))
            return task, stream

    async def get(self, params: dict) -> Task:
        with tracer.start_as_current_span("a2a.tasks.get"):
            task_id = _require_id(params)
            history_length = params.get("historyLength")
            if history_length is not None and (
                not isinstance(history_length, int) or isinstance(history_length, bool) or history_length < 0
            ):
                raise InvalidParamsError("params.historyLength must be a non-negative integer")
            task = await self.store.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"No task with id {task_id}")
            if history_length is not None:
                # history[-0:] is the whole list, so 0 needs its own case.
                history = task.history[-history_length:] if history_length else []
                task = task.model_copy(update={"history": history})
            return task

    async def cancel(self, params: dict) -> Task:
        with tracer.start_as_current_span("a2a.tasks.cancel"):
            task_id = _require_id(params)
            # States only move forward (submitted -> working -> terminal), so
            # a lost CAS means the state advanced; re-read and decide again.
            # At most one retry can be caused by submitted -> working.
            for _ in range(3):
                task = await self.store.get(task_id)
                if task is None:
                    raise TaskNotFoundError(f"No task with id {task_id}")
                if task.status.state.is_terminal:
                    raise TaskNotCancelableError(f"Task {task_id} is already {task.status.state.value}")
                canceled = task.with_status(TaskState.CANCELED)
                if await self.store.transition(task_id, _CANCELABLE, canceled):
                    self._active.discard(task_id)
                    logger.info("a2a.task.canceled task_id=%s", task_id)
                    self.broadcaster.publish(task_id, _status_event(canceled, final=True))
                    return canceled
            raise TaskNotCancelableError(f"Task {task_id} changed state while canceling")

    async def cancel_if_active(self, task_id: str) -> bool:
        """Cancel `task_id` unless it already finished or vanished. Used when
        the client that started a scan goes away (/ws/scan disconnect)."""
        try:
            await self.cancel({"id": task_id})
            return True
        except (TaskNotCancelableError, TaskNotFoundError):
            return False

    async def resubscribe(self, params: dict) -> EventStream:
        with tracer.start_as_current_span("a2a.tasks.resubscribe"):
            task_id = _require_id(params)
            # Subscribe *before* reading the store: a final event published
            # between a read and a later subscribe would otherwise be lost and
            # the stream would hang. Whatever the read then shows, the stream
            # either already holds the terminal state or will receive it.
            stream = self.open_stream(task_id)
            try:
                task = await self.store.get(task_id)
            except BaseException:
                await stream.aclose()
                raise
            if task is None:
                await stream.aclose()
                raise TaskNotFoundError(f"No task with id {task_id}")
            return stream

    # ---- streaming ----------------------------------------------------------

    def open_stream(self, task_id: str, snapshot: Task | None = None) -> EventStream:
        """Subscribe now; the returned stream yields a Task snapshot (`snapshot`,
        or the store's current copy read *after* subscribing), then events."""
        return EventStream(
            self.broadcaster, task_id, lambda queue: self._stream_events(task_id, queue, snapshot)
        )

    async def _stream_events(
        self, task_id: str, queue: asyncio.Queue, snapshot: Task | None = None
    ) -> AsyncIterator[Any]:
        """Task snapshot first, then broadcast events until a final one.

        Every heartbeat interval without events re-reads the store: a task
        executing on another instance (or orphaned by a crashed one) never
        publishes here, so the store is the only way such a stream can learn
        it ended. A hard lifetime cap ends any stream that still hasn't."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.stream_max_seconds
        if snapshot is None:
            snapshot = await self.store.get(task_id)
        if snapshot is None:
            return
        yield snapshot.model_dump(mode="json")
        if snapshot.status.state.is_terminal:
            yield _status_event(snapshot, final=True)
            return
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.info("a2a.stream.max_lifetime_reached task_id=%s", task_id)
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=min(self.heartbeat_interval, remaining))
            except asyncio.TimeoutError:
                current = await self.store.get(task_id)
                if current is None:
                    return
                if current.status.state.is_terminal:
                    for terminal_event in _terminal_events(current):
                        yield terminal_event
                    return
                yield HEARTBEAT
                continue
            yield event
            if event.get("final"):
                return

    # ---- creation & execution -------------------------------------------------

    async def _create_or_replay(self, params: dict) -> tuple[Task, bool]:
        target_path = _extract_target_path(params)
        metadata_in = _as_object(params, "metadata")
        task_id = _extract_task_id(params) or new_task_id()
        context_id = _extract_context_id(params)
        # Only allow-listed keys are stored; the rest of the caller's
        # metadata is dropped rather than persisted verbatim.
        kept_metadata = {k: metadata_in[k] for k in limits.ALLOWED_METADATA_KEYS if k in metadata_in}

        message = Message(
            role="user",
            taskId=task_id,
            contextId=context_id,
            parts=[Part(kind="text", text=target_path)],
            metadata=kept_metadata or None,
        )
        task = Task(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            history=[message],
            metadata={
                "target_path": target_path,
                "include_red_team": bool(metadata_in.get("include_red_team", False)),
                "include_llm_auditor": bool(metadata_in.get("include_llm_auditor", False)),
                "created_at": now_iso(),
            },
        )
        # The lock makes check-then-create atomic within this process, so
        # concurrent submissions can't overshoot the active-task cap.
        async with self._create_lock:
            if len(self._active) >= self.max_active_tasks:
                existing = await self.store.get(task_id)
                if existing is None:
                    raise ServerBusyError(
                        f"Too many active tasks (limit {self.max_active_tasks}); retry later"
                    )
                stored, created = existing, False  # idempotent replay is still answered
            else:
                stored, created = await self.store.create_if_absent(task)
                if created:
                    self._active.add(task_id)
        if created:
            logger.info("a2a.task.submitted task_id=%s target=%s", task_id, target_path)
        else:
            stored = stored.model_copy(update={"metadata": {**stored.metadata, "idempotentReplay": True}})
            logger.info("a2a.task.idempotent_replay task_id=%s", task_id)
        return stored, created

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def _execute(self, task_id: str) -> None:
        with tracer.start_as_current_span("a2a.tasks.execute"):
            try:
                async with self._admission:
                    await self._execute_admitted(task_id)
            finally:
                self._active.discard(task_id)

    def _canceled_in_store(self, task_id: str, loop: asyncio.AbstractEventLoop) -> bool:
        """Called from the worker thread. Never blocks indefinitely: if the
        loop can't answer within the timeout (busy, shutting down, store
        unreachable), skip this checkpoint — the final CAS still guarantees
        a canceled task is never overwritten."""
        future = None
        try:
            future = asyncio.run_coroutine_threadsafe(self.store.get(task_id), loop)
            current = future.result(timeout=self.progress_check_timeout)
        except Exception as exc:  # noqa: BLE001 - advisory check, see docstring
            if future is not None and not loop.is_closed():
                future.cancel()
            logger.warning("a2a.task.cancel_check_skipped task_id=%s reason=%s", task_id, type(exc).__name__)
            return False
        return current is not None and current.status.state == TaskState.CANCELED

    async def _execute_admitted(self, task_id: str) -> None:
        loop = asyncio.get_running_loop()
        task = await self.store.get(task_id)
        if task is None or task.status.state.is_terminal:
            return

        working = task.with_status(TaskState.WORKING)
        if not await self.store.transition(task_id, {TaskState.SUBMITTED}, working):
            return  # canceled while waiting for admission
        logger.info("a2a.task.working task_id=%s", task_id)
        self.broadcaster.publish(task_id, _status_event(working, final=False))

        metadata = working.metadata

        def on_progress(event: dict) -> None:
            if self._canceled_in_store(task_id, loop):
                raise _TaskCanceled()
            self.broadcaster.publish(task_id, _progress_event(working, event))

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
            attestation, red_team_result = await loop.run_in_executor(self._executor, run_pipeline)
        except _TaskCanceled:
            logger.info("a2a.task.canceled_during_execution task_id=%s", task_id)
            return
        except Exception as exc:  # noqa: BLE001 - pipeline failures become a task-level failure, not a crash
            logger.exception("a2a.task.failed task_id=%s", task_id)
            failed = working.with_status(TaskState.FAILED, message=_error_message(str(exc)))
            if await self.store.transition(task_id, {TaskState.WORKING}, failed):
                self.broadcaster.publish(task_id, _status_event(failed, final=True))
            return

        result = _attestation_to_result(attestation, red_team_result)
        artifact = Artifact(name="attestation", parts=[Part(kind="data", data=result)])
        # Built from the WORKING snapshot we wrote: if the CAS succeeds, the
        # stored task was still exactly that snapshot (any other write changes
        # the state), so nothing is lost by not re-reading it.
        completed = working.model_copy(update={"artifacts": [artifact]}).with_status(TaskState.COMPLETED)
        if not await self.store.transition(task_id, {TaskState.WORKING}, completed):
            logger.info("a2a.task.completion_discarded task_id=%s (canceled first)", task_id)
            return
        logger.info("a2a.task.completed task_id=%s verdict=%s", task_id, attestation.verdict)
        self.broadcaster.publish(task_id, _artifact_event(completed, artifact))
        self.broadcaster.publish(task_id, _status_event(completed, final=True))
