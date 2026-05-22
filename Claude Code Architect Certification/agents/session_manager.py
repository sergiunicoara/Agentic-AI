"""
CCA-F D1.7: Session Management
Exam concepts:
- Named session resumption
- fork_session for divergent exploration
- Stale context detection
- Session continuity across reconnects
"""
from __future__ import annotations
import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_DIR = Path(".claude/sessions")
STALE_THRESHOLD_SECONDS = 1800  # 30 minutes


@dataclass
class SessionState:
    session_id: str
    ticket_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    status: str = "active"  # active | suspended | complete | stale
    parent_id: str | None = None  # set for forked sessions


class SessionManager:
    """
    D1.7: Named session management for resumable investigations.

    Exam concepts:
    - Named sessions: resume investigation across disconnects
    - fork_session: explore divergent hypotheses without losing main thread
    - Stale detection: sessions idle >30min need re-grounding before continuing
    """

    def __init__(self):
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def create(self, ticket_id: str) -> SessionState:
        """Create a new named investigation session."""
        session_id = f"inv_{ticket_id}_{int(time.time())}"
        state = SessionState(session_id=session_id, ticket_id=ticket_id)
        self._save(state)
        logger.info(f"Created session {session_id} for ticket {ticket_id}")
        return state

    def resume(self, session_id: str) -> SessionState:
        """
        D1.7: Resume a named session.
        Checks for stale context before resuming.
        """
        state = self._load(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")

        idle = time.time() - state.last_activity
        if idle > STALE_THRESHOLD_SECONDS:
            # D1.7: Stale context handling — don't silently continue stale state
            logger.warning(f"Session {session_id} is stale ({idle/60:.0f}min idle) — re-grounding needed")
            state.status = "stale"
            state.messages.append({
                "role": "user",
                "content": f"[SESSION RESUMED after {idle/60:.0f} minutes. "
                           f"Re-ground yourself: review the preserved facts and continue.] "
                           f"Preserved facts: {json.dumps(state.facts)}"
            })

        state.last_activity = time.time()
        state.status = "active"
        self._save(state)
        return state

    def fork(self, base_session_id: str, label: str) -> SessionState:
        """
        D1.7: Fork a session for divergent exploration.
        Use when exploring a different hypothesis without losing the main thread.
        Example: main thread suspects DB issue, fork to explore network issue.
        """
        base = self._load(base_session_id)
        if not base:
            raise ValueError(f"Base session {base_session_id} not found")

        fork_id = f"{base_session_id}_fork_{label}_{int(time.time())}"
        forked = SessionState(
            session_id=fork_id,
            ticket_id=base.ticket_id,
            messages=base.messages.copy(),  # start from same point
            facts=base.facts.copy(),
            parent_id=base_session_id,
            status="active",
        )
        self._save(forked)
        logger.info(f"Forked session {base_session_id} → {fork_id} (label: {label})")
        return forked

    def update(self, state: SessionState):
        """Persist session state after each turn."""
        state.last_activity = time.time()
        self._save(state)

    def complete(self, session_id: str):
        state = self._load(session_id)
        if state:
            state.status = "complete"
            self._save(state)

    def _save(self, state: SessionState):
        path = SESSION_DIR / f"{state.session_id}.json"
        path.write_text(json.dumps(asdict(state), indent=2))

    def _load(self, session_id: str) -> SessionState | None:
        path = SESSION_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return SessionState(**data)
