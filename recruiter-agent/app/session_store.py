# app/session_store.py — Session persistence with Redis + SQLite fallback
#
# Priority:
#   1. Redis  (if REDIS_URL env var is set and connection succeeds)
#   2. SQLite (always available; /tmp/sessions.db by default)
#
# The public API is unchanged:
#   load_session(session_id) -> Optional[State]
#   save_session(session_id, state) -> None
#
# Redis keys: "recruiter:session:<id>"  TTL = SESSION_TTL_SECONDS (default 24h)
# Redis failure at runtime falls back to SQLite silently (logged at WARNING).

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Optional

from .models.state import State

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("SESSION_DB_PATH", "/tmp/sessions.db")
_SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", str(24 * 3600)))  # 24 hours

# ── Redis ─────────────────────────────────────────────────────────────────────

_redis_client = None
_redis_available: Optional[bool] = None   # None = not yet tried


def _get_redis():
    """
    Return a connected redis client or None.
    Probes once on first call; if Redis is unavailable it stays None for the
    process lifetime (avoids hammering a broken connection on every request).
    """
    global _redis_client, _redis_available

    # Already determined
    if _redis_available is False:
        return None
    if _redis_client is not None:
        return _redis_client

    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        _redis_available = False
        return None

    try:
        import redis as redis_lib  # redis[hiredis] or plain redis
        client = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()  # verify reachability at startup
        _redis_client = client
        _redis_available = True
        logger.info("session_store: Redis connected (%s)", url)
        return _redis_client
    except ImportError:
        logger.warning(
            "session_store: redis package not installed, falling back to SQLite"
        )
        _redis_available = False
        return None
    except Exception as exc:
        logger.warning(
            "session_store: Redis unavailable (%s), falling back to SQLite", exc
        )
        _redis_available = False
        return None


def _redis_key(session_id: str) -> str:
    return f"recruiter:session:{session_id}"


# ── SQLite fallback ───────────────────────────────────────────────────────────

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


# ── Public API ────────────────────────────────────────────────────────────────

def load_session(session_id: str) -> Optional[State]:
    """Load session state. Returns None if session does not exist."""
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(_redis_key(session_id))
            if raw:
                return State.model_validate(json.loads(raw))
            return None
        except Exception as exc:
            logger.warning(
                "session_store: Redis load failed for %s (%s), trying SQLite",
                session_id, exc,
            )

    # SQLite path
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT state_json FROM sessions WHERE id = ?", (session_id,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return State.model_validate(json.loads(row[0]))
    except Exception as exc:
        logger.error("session_store: SQLite load failed for %s: %s", session_id, exc)
        return None


def save_session(session_id: str, state: State) -> None:
    """Persist session state. Redis TTL = SESSION_TTL_SECONDS."""
    state_json = state.model_dump_json()

    r = _get_redis()
    if r is not None:
        try:
            r.set(_redis_key(session_id), state_json, ex=_SESSION_TTL)
            return
        except Exception as exc:
            logger.warning(
                "session_store: Redis save failed for %s (%s), falling back to SQLite",
                session_id, exc,
            )

    # SQLite fallback
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, state_json) VALUES (?, ?)",
            (session_id, state_json),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("session_store: SQLite save failed for %s: %s", session_id, exc)


def delete_session(session_id: str) -> None:
    """Remove a session from both stores (best-effort, used for testing/cleanup)."""
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_redis_key(session_id))
        except Exception:
            pass

    try:
        conn = _get_conn()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def session_store_info() -> dict:
    """Return a diagnostic dict (used by health/status endpoints)."""
    r = _get_redis()
    return {
        "backend": "redis" if r is not None else "sqlite",
        "redis_url": bool(os.environ.get("REDIS_URL")),
        "sqlite_path": DB_PATH,
        "session_ttl_seconds": _SESSION_TTL,
    }
