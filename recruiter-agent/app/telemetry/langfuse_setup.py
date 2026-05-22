# app/telemetry/langfuse_setup.py
"""
Langfuse initialisation — single place for the SDK client.

Enabled when LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY are set.
Everything degrades silently to no-ops when the keys are absent,
so the agent works identically with or without Langfuse.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client: Optional[object] = None
_initialised = False


def get_langfuse():
    """Return a live Langfuse client or None."""
    global _client, _initialised
    if _initialised:
        return _client

    _initialised = True
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()

    if not pk or not sk:
        logger.info("Langfuse disabled — LANGFUSE_PUBLIC_KEY / SECRET_KEY not set")
        return None

    try:
        from langfuse import Langfuse
        _client = Langfuse(public_key=pk, secret_key=sk, host=host)
        logger.info("Langfuse enabled → %s", host)
    except Exception as exc:
        logger.warning("Langfuse init failed: %s", exc)

    return _client


def flush() -> None:
    """Flush pending events — call on shutdown."""
    lf = get_langfuse()
    if lf:
        try:
            lf.flush()  # type: ignore[attr-defined]
        except Exception:
            pass
