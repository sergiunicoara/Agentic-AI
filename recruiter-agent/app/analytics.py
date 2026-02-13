# app/analytics.py

from __future__ import annotations
import json
import logging
import time
from typing import Any, Dict, Optional

# Cloud Run auto-parses JSON logs if you log to stdout
logger = logging.getLogger("analytics")
logger.setLevel(logging.INFO)


def emit(event: str, payload: Optional[Dict[str, Any]] = None) -> None:
    """
    Minimal analytics emission: event + payload → stdout as JSON.
    Aligned with Google Agents course: log intent, tools, outcome.
    """
    try:
        record = {
            "ts": time.time(),
            "event": event,
            "payload": payload or {},
        }
        logger.info(json.dumps(record))
    except Exception:
        # Never break the agent because of telemetry
        pass
