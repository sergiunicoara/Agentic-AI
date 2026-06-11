from __future__ import annotations

"""Thread-safe OpenSearch client singleton.

The client is intentionally lazy — it is created on first access so the
application can start even when OPENSEARCH_URL is empty (mock/CI mode).
Callers must check ``is_available()`` before issuing queries.

Availability is re-probed on a cooldown: if OpenSearch was down when the
process started (common — the API boots faster than the JVM), dual-write
recovers automatically once the cluster comes up instead of staying
disabled for the life of the process.
"""

import threading
import time
from typing import Optional

from app.core.config import settings
from app.core.observability import emit_event

_lock = threading.Lock()
_client: Optional[object] = None
_available: bool = False
_last_probe: float = 0.0

# Re-check a down cluster at most every 30s so the probe cost stays negligible.
PROBE_COOLDOWN_S = 30.0


def _make_client():
    try:
        from opensearchpy import OpenSearch  # type: ignore
    except ImportError:
        raise RuntimeError("opensearch-py not installed. Run: pip install opensearch-py==2.6.0")

    url = settings.opensearch_url.rstrip("/")
    # Parse host/port from URL (supports http://host:port)
    url_clean = url.replace("http://", "").replace("https://", "")
    use_ssl = url.startswith("https://")
    host, _, port_str = url_clean.partition(":")
    port = int(port_str) if port_str else (443 if use_ssl else 9200)

    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_compress=True,
        use_ssl=use_ssl,
        verify_certs=False,
        timeout=int(settings.opensearch_timeout_s),
        max_retries=3,
        retry_on_timeout=True,
    )


def _probe(client) -> bool:
    global _available, _last_probe
    _last_probe = time.time()
    try:
        info = client.info()
        if not _available:
            emit_event("opensearch_connected", {
                "version": info.get("version", {}).get("number", "unknown"),
                "cluster": info.get("cluster_name", "unknown"),
            })
        _available = True
    except Exception as e:
        if _available:
            emit_event("opensearch_unavailable", {"error": str(e)})
        _available = False
    return _available


def get_client():
    """Return the shared OpenSearch client. Raises if not configured."""
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        if not settings.opensearch_url:
            raise RuntimeError("OPENSEARCH_URL not configured")
        client = _make_client()
        _probe(client)
        _client = client
        return _client


def is_available() -> bool:
    """Return True if OpenSearch is configured and reachable.

    Re-probes a down cluster after PROBE_COOLDOWN_S so transient startup
    outages self-heal without a process restart.
    """
    if not settings.opensearch_url:
        return False
    if _client is None:
        try:
            get_client()
        except Exception:
            return False
        return _available
    if not _available and (time.time() - _last_probe) >= PROBE_COOLDOWN_S:
        with _lock:
            if not _available and (time.time() - _last_probe) >= PROBE_COOLDOWN_S:
                _probe(_client)
    return _available


def reset() -> None:
    """Reset singleton — used in tests."""
    global _client, _available, _last_probe
    with _lock:
        _client = None
        _available = False
        _last_probe = 0.0
