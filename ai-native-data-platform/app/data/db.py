"""
Compatibility shim for database access.

This module provides stable imports for legacy code:

    from app.db import SessionLocal, engine, session_scope

The real implementation lives in app.data.db and supports routing,
replicas, and scoped session helpers.
"""

from __future__ import annotations

# Public session helpers (preferred modern API)
from app.data.db import (
    session_scope,
    write_session_scope,
    read_session_scope,
)

# Internal access to implementation details
from app.data import db as _db


# --- Primary database binding (backwards compatibility) ---

# Resolve the primary database URL
_primary_url = _db._primary_url()

# Ensure engine + sessionmaker are initialized and cached
SessionLocal = _db._get_sessionmaker(_primary_url)

# Extract the engine from the cache populated above
engine = _db._engine_cache[_primary_url][0]


__all__ = [
    "SessionLocal",
    "engine",
    "session_scope",
    "write_session_scope",
    "read_session_scope",
]
