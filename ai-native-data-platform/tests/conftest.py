"""Pytest configuration for unit tests.

app/data/db.py has a circular self-import that only triggers when the module
is first loaded in isolation (outside the normal FastAPI startup order).

We inject a stub BEFORE any app module is collected so the import chain
contracts.py → observability.py → app.data.db never touches the real file.
All tests that need a real DB (integration tests) should override this stub
via their own fixtures.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal env vars — must be set before any app.core.config import
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://app:app@localhost/app")
os.environ.setdefault("REDIS_URL", "")

# ---------------------------------------------------------------------------
# DB stub — a fully initialized mock that satisfies all import-time consumers
# ---------------------------------------------------------------------------

@contextmanager
def _noop_session(*args, **kwargs):
    yield MagicMock()


_db_stub = MagicMock()
_db_stub.write_session_scope = _noop_session
_db_stub.read_session_scope = _noop_session
_db_stub.session_scope = _noop_session
_db_stub.SessionLocal = MagicMock()
_db_stub.engine = MagicMock()

# Inject before Python's import machinery touches the real file.
# setdefault: no-op if a real module was already loaded (e.g., integration tests).
sys.modules.setdefault("app.data.db", _db_stub)
