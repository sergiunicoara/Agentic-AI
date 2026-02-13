from enum import Enum
from pydantic import BaseModel
from typing import List, Dict, Any


class StepKind(str, Enum):
    user = "user"
    agent = "agent"
    tool = "tool"


class Step(BaseModel):
    kind: StepKind
    message: str
    meta: Dict[str, Any] | None = None


class Trajectory(BaseModel):
    steps: List[Step]

    def add(self, kind: StepKind, message: str, meta: Dict[str, Any] | None = None):
        self.steps.append(Step(kind=kind, message=message, meta=meta))

    def to_dict(self) -> Dict[str, Any]:
        return {"steps": [s.dict() for s in self.steps]}
