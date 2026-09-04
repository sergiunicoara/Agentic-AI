"""Timestamp default shared by every model.

The columns are ``TIMESTAMP WITHOUT TIME ZONE`` holding UTC, so the default has
to produce a naive value. ``datetime.utcnow`` does that but is deprecated in
3.12; this is the non-deprecated spelling of the same instant.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
