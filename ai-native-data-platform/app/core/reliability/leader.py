from __future__ import annotations

"""Leader election via Postgres advisory locks.

We run multiple API replicas. Some background controllers should run only once
cluster-wide (e.g., remediation). We use a Postgres advisory lock as a
lightweight leader election.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.data.db import engine


@dataclass
class LeaderLock:
    """Cluster-wide leader lock."""

    key: int
    connection: Any | None = None


def try_acquire(lock: LeaderLock) -> bool:
    """Try to acquire the leader lock. Returns True if acquired."""

    if lock.connection is not None:
        return True
    connection = engine.connect()
    try:
        row = connection.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": int(lock.key)}).fetchone()
        if row and row[0]:
            lock.connection = connection
            return True
    except Exception:
        connection.close()
        raise
    connection.close()
    return False


def release(lock: LeaderLock) -> None:
    """Release the lock if held by this session."""
    if lock.connection is None:
        return
    try:
        lock.connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(lock.key)})
    finally:
        lock.connection.close()
        lock.connection = None
