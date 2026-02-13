from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.quality import Trajectory


class State(BaseModel):
    source: Optional[str] = None
    role: Optional[str] = None
    criteria: List[str] = Field(default_factory=list)

    # Conversation memory (you can structure this later)
    memory: List[Dict[str, Any]] = Field(default_factory=list)

    # Trajectory for observability/eval
    trajectory: Trajectory = Field(default_factory=lambda: Trajectory(steps=[]))

    extra: Dict[str, Any] = Field(default_factory=dict)
