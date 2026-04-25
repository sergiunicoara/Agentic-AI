from __future__ import annotations

"""Database session management.

Provides three context managers used throughout the platform:
  - write_session_scope()          — always routes to the primary (write) DB
  - read_session_scope(region=...) — routes to a healthy read replica when
                                     replica_database_urls is configured,
                                     falls back to primary otherwise
  - session_scope()                — alias for write_session_scope (compat)

Engine and sessionmaker instances are cached per URL so each DSN gets a
single connection pool for the lifetime of the process.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Internal engine cache  {url: (engine, sessionmaker)}
# ---------------------------------------------------------------------------

_engine_cache: dict[str, tuple] = {}


def _primary_url() -> str:
    return settings.primary_database_url or settings.database_url


def _replica_urls() -> list[str]:
    raw = settings.replica_database_urls or ""
    return [u.strip() for u in raw.split(",") if u.strip()]


def _get_sessionmaker(url: str) -> sessionmaker:
    if url not in _engine_cache:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
        )
        sm = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        _engine_cache[url] = (engine, sm)
    return _engine_cache[url][1]


# ---------------------------------------------------------------------------
# Public exports for backwards-compatible imports (app.db shim)
# ---------------------------------------------------------------------------

SessionLocal = _get_sessionmaker(_primary_url())
engine = _engine_cache[_primary_url()][0]


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------

@contextmanager
def session_scope(url: str | None = None) -> Generator[Session, None, None]:
    """Write session (alias kept for backwards compatibility).

    Accepts an optional URL so callers that manage their own DSN (e.g. shard
    retrievers) can reuse the same engine-cache logic without a separate helper.
    """
    sm = _get_sessionmaker(url or _primary_url())
    session: Session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def write_session_scope() -> Generator[Session, None, None]:
    """Session pinned to the primary (write) database."""
    with session_scope() as s:
        yield s


@contextmanager
def read_session_scope(region: str | None = None) -> Generator[Session, None, None]:
    """Session for read operations.

    Routes to a read replica when replica_database_urls is configured and a
    replica is healthy (lag < max_replica_lag_seconds). Falls back to the
    primary when no healthy replica is available.

    The `region` parameter is reserved for future geo-aware routing.
    """
    replicas = _replica_urls()
    url = _primary_url()

    if replicas:
        # Try the first replica that reports acceptable lag.
        for replica_url in replicas:
            try:
                sm = _get_sessionmaker(replica_url)
                probe = sm()
                lag = probe.execute(
                    text("SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))")
                ).scalar() or 0.0
                probe.close()
                if float(lag) <= settings.max_replica_lag_seconds:
                    url = replica_url
                    break
            except Exception:
                continue  # replica unreachable — try next

    sm = _get_sessionmaker(url)
    session: Session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "SessionLocal",
    "engine",
    "session_scope",
    "write_session_scope",
    "read_session_scope",
]
