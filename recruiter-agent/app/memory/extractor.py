from __future__ import annotations

from typing import Any, Dict, List

from app.models.state import State


def extract_memories_from_turn(
    state: State, user_message: str, agent_reply: str
) -> List[Dict[str, Any]]:
    """Very small heuristic-based memory extractor.

    In a real system you might call an LLM here. For the course-aligned
    project we keep this deterministic and cheap: we capture things like
    role, criteria, and notable recruiter insights as structured memories.
    """
    memories: List[Dict[str, Any]] = []

    if state.role:
        memories.append(
            {
                "kind": "role",
                "payload": {"role": state.role},
            }
        )

    if state.criteria:
        memories.append(
            {
                "kind": "criteria",
                "payload": {"criteria": state.criteria},
            }
        )

    # Capture a lightweight summary of the last reply for future personalization.
    if agent_reply:
        memories.append(
            {
                "kind": "agent_reply_summary",
                "payload": {
                    "snippet": agent_reply[:280],
                    "source": "recruiter_agent",
                },
            }
        )

    return memories
