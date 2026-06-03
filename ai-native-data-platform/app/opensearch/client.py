from __future__ import annotations

"""Thread-safe OpenSearch client singleton.

The client is intentionally lazy — it is created on first access so the
application can start even when OPENSEARCH_URL is empty (mock/CI mode).
Callers must check ``is_available()`` before issuing queries.
"""

import threading
from typing import Optional

from app.core.config import settings
from app.core.observability import emit_event

_lock = threading.Lock()
_client: Optional[object] = None
_available: bool = False


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


def get_client():
    """Return the shared OpenSearch client. Raises if not available."""
    global _client, _available
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        if not settings.opensearch_url:
            raise RuntimeError("OPENSEARCH_URL not configured")
        _client = _make_client()
        try:
            info = _client.info()
            _available = True
            emit_event("opensearch_connected", {
                "version": info.get("version", {}).get("number", "unknown"),
                "cluster": info.get("cluster_name", "unknown"),
            })
        except Exception as e:
            _available = False
            emit_event("opensearch_unavailable", {"error": str(e)})
        return _client


def is_available() -> bool:
    """Return True if OpenSearch is configured and reachable."""
    global _available
    if not settings.opensearch_url:
        return False
    if _client is None:
        try:
            get_client()
        except Exception:
            return False
    return _available


def reset() -> None:
    """Reset singleton — used in tests."""
    global _client, _available
    with _lock:
        _client = None
        _available = False
