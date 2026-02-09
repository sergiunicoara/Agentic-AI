from __future__ import annotations

"""Leader election via Postgres advisory locks.

We run multiple API replicas. Some background controllers should run only once
cluster-wide (e.g., remediation). We use a Postgres advisory lock as a
lightweight leader election.
"""

from dataclasses import dataclass

from sqlalchemy import text

from app.data.db import write_session_scope


@dataclass(frozen=True)
class LeaderLock:
    """Cluster-wide leader lock."""

    key: int


def try_acquire(lock: LeaderLock) -> bool:
    """Try to acquire the leader lock. Returns True if acquired."""

    with write_session_scope() as db:
        row = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": int(lock.key)}).fetchone()
        return bool(row and row[0])


def release(lock: LeaderLock) -> None:
    """Release the lock if held by this session."""
    with write_session_scope() as db:
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(lock.key)})
