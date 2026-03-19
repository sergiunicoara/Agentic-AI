from __future__ import annotations

import datetime
import uuid

from sqlalchemy import text

from app.data.db import read_session_scope

# Hard ceiling on query execution time — protects the shared DB under load.
_TIMEOUT_MS = 5000


def execute_query(sql: str, params: dict) -> list[dict]:
    """Execute a read-only parameterized query and return rows as dicts.

    Enforces a per-query statement_timeout so runaway analytical queries
    cannot starve the online retrieval path.
    """
    with read_session_scope() as db:
        db.execute(text(f"SET LOCAL statement_timeout = '{_TIMEOUT_MS}'"))
        result = db.execute(text(sql), params)
        cols = list(result.keys())
        rows = result.fetchmany(1000)

    return [
        {col: _serialize(val) for col, val in zip(cols, row)}
        for row in rows
    ]


def _serialize(v: object) -> object:
    """Convert non-JSON-serializable DB values to strings."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return str(v)
