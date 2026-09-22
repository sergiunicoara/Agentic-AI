"""
A2A protocol data model (spec-shaped Task/Message/Artifact types).

Sentinel is a single-shot, single-turn agent: a task is submitted once,
runs to completion (or failure/cancellation), and never asks the caller
for more input mid-task. So of the full TaskState enum defined by the
A2A spec, only five states are ever produced here:

    submitted -> working -> completed | failed | canceled

`input-required`, `auth-required`, `rejected`, and `unknown` are valid
per spec but intentionally unused — there is no multi-turn interaction
for a security scan to pause on.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:12]}"


class Part(BaseModel):
    """A single content part of a Message or Artifact (text or structured data)."""

    kind: Literal["text", "data"] = "text"
    text: str | None = None
    data: dict[str, Any] | None = None


class Message(BaseModel):
    kind: Literal["message"] = "message"
    messageId: str = Field(default_factory=new_message_id)
    contextId: str | None = None
    taskId: str | None = None
    role: Literal["user", "agent"] = "user"
    parts: list[Part] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class Artifact(BaseModel):
    artifactId: str = Field(default_factory=lambda: f"artifact_{uuid.uuid4().hex[:12]}")
    name: str | None = None
    parts: list[Part] = Field(default_factory=list)


class TaskStatus(BaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: str = Field(default_factory=now_iso)


class Task(BaseModel):
    kind: Literal["task"] = "task"
    id: str
    contextId: str | None = None
    status: TaskStatus
    history: list[Message] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def with_status(self, state: TaskState, message: Message | None = None) -> "Task":
        """Return a copy transitioned to `state`, appending the transition to history."""
        status = TaskStatus(state=state, message=message)
        history = list(self.history)
        if message is not None:
            history.append(message)
        return self.model_copy(update={"status": status, "history": history})
