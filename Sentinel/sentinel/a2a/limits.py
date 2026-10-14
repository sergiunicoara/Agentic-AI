"""
Resource limits for the A2A layer, read from the environment.

Every limit here bounds something an unauthenticated (or merely
over-eager) caller could otherwise grow without limit on a server that
binds 0.0.0.0: pipeline threads, stored tasks, request bodies, and
open streams. They are read at call time rather than import time so
`TaskService` instances (and tests) pick up the current environment.

  SENTINEL_MAX_CONCURRENT_SCANS  pipeline runs executing at once (A2A + /ws/scan)  default 2
  SENTINEL_MAX_ACTIVE_TASKS      non-terminal tasks this process accepts           default 20
  SENTINEL_MAX_BODY_BYTES        HTTP request body size                            default 1 MiB
  SENTINEL_STREAM_MAX_SECONDS    lifetime of one SSE / WebSocket event stream      default 1800
"""
from __future__ import annotations

import os

DEFAULT_MAX_CONCURRENT_SCANS = 2
DEFAULT_MAX_ACTIVE_TASKS = 20
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_STREAM_MAX_SECONDS = 30 * 60

# Metadata keys a caller may set on a task. Anything else is dropped before
# the task is stored, so callers can't park arbitrary data in the task store.
ALLOWED_METADATA_KEYS = ("target_path", "include_red_team", "include_llm_auditor", "task_id")


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


def max_concurrent_scans() -> int:
    return _positive_int("SENTINEL_MAX_CONCURRENT_SCANS", DEFAULT_MAX_CONCURRENT_SCANS)


def max_active_tasks() -> int:
    return _positive_int("SENTINEL_MAX_ACTIVE_TASKS", DEFAULT_MAX_ACTIVE_TASKS)


def max_body_bytes() -> int:
    return _positive_int("SENTINEL_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)


def stream_max_seconds() -> int:
    return _positive_int("SENTINEL_STREAM_MAX_SECONDS", DEFAULT_STREAM_MAX_SECONDS)
