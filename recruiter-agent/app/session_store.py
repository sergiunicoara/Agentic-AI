# app/session_store.py
from __future__ import annotations

from typing import Dict, Any, Optional
import json
import os
import sqlite3

from .models.state import State

DB_PATH = os.environ.get("SESSION_DB_PATH", "/tmp/sessions.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
        """
    )
    return conn


def load_session(session_id: str) -> Optional[State]:
    conn = _get_conn()
    cur = conn.execute("SELECT state_json FROM sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None

    data = json.loads(row[0])
    # We assume State has a .model_validate or similar; if not, adjust:
    return State.model_validate(data)  # Pydantic v2


def save_session(session_id: str, state: State) -> None:
    conn = _get_conn()
    state_json = state.model_dump_json()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, state_json) VALUES (?, ?)",
        (session_id, state_json),
    )
    conn.commit()
    conn.close()
