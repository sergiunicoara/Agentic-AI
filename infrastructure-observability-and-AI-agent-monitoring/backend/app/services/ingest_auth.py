"""Authentication helpers for agent telemetry ingestion."""

import hmac
import json

from app.config import settings


def valid_emit_key(api_key: str, agent_name: str) -> bool:
    """Use per-agent keys when configured; the shared key is dev-only."""
    if not api_key:
        return False
    if settings.emit_agent_keys:
        try:
            keys = json.loads(settings.emit_agent_keys)
            expected = keys.get(agent_name, "")
            return bool(expected) and hmac.compare_digest(api_key, str(expected))
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
    return bool(settings.emit_api_key) and hmac.compare_digest(api_key, settings.emit_api_key)
