from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StepKind(str, Enum):
    user = "user"
    agent = "agent"
    tool = "tool"


class Step(BaseModel):
    kind: StepKind
    message: str
    meta: Optional[Dict[str, Any]] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z"
    )


class Trajectory(BaseModel):
    session_id: str = ""
    steps: List[Step] = Field(default_factory=list)

    def add(
        self,
        kind: StepKind,
        message: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.steps.append(Step(kind=kind, message=message, meta=meta))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": sum(1 for s in self.steps if s.kind == StepKind.user),
            "steps": [s.dict() for s in self.steps],
        }
