# app/telemetry/langfuse_setup.py
"""
Langfuse v4 initialisation.

In v4, the SDK auto-reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST
from env vars. Calling Langfuse() explicitly sets the global client used by
@observe decorators throughout the app.

Degrades silently to no-ops when keys are absent.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialised = False


def init_langfuse() -> None:
    """Call once at startup. No-op if keys are missing."""
    global _initialised
    if _initialised:
        return
    _initialised = True

    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()

    if not pk or not sk:
        logger.info("Langfuse disabled — LANGFUSE_PUBLIC_KEY / SECRET_KEY not set")
        return

    try:
        from langfuse import Langfuse
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
        Langfuse(public_key=pk, secret_key=sk, host=host)
        logger.info("Langfuse v4 enabled → %s", host)
    except Exception as exc:
        logger.warning("Langfuse init failed: %s", exc)


def flush() -> None:
    """Flush pending events — call on shutdown."""
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception:
        pass
