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
from urllib.parse import urlsplit

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

    # urlsplit (stdlib) instead of the previous hand-rolled
    # .replace("http://", "").replace("https://", "") + partition(":") —
    # that approach broke on embedded basic-auth credentials
    # (https://user:pass@host:port, the same convention DATABASE_URL/
    # REDIS_URL already use in this codebase), IPv6 hosts, and any path
    # component (e.g. a reverse proxy prefix), and had no way to extract
    # credentials at all even if it had parsed the host/port correctly.
    parsed = urlsplit(settings.opensearch_url.rstrip("/"))
    use_ssl = parsed.scheme == "https"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if use_ssl else 9200)
    http_auth = (parsed.username, parsed.password) if parsed.username else None

    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=http_auth,
        http_compress=True,
        use_ssl=use_ssl,
        # Secure by default: a real https:// endpoint (e.g. a managed
        # OpenSearch service) gets real certificate validation, not a
        # blanket "trust any certificate" that also silently accepts a
        # MITM'd connection. opensearch_verify_certs exists as an explicit,
        # opt-in escape hatch for a self-signed cert in local/test setups —
        # never the unconditional default.
        verify_certs=settings.opensearch_verify_certs if use_ssl else False,
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
