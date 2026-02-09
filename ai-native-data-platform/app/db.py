"""Compatibility shim.

The rewritten scaffold organizes state under app.data.* and app.core.*.
Existing modules (and external users) may still import app.db.
"""

from app.data.db import SessionLocal, engine, session_scope  # noqa: F401
