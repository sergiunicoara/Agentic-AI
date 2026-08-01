"""Protection for internal, cost-bearing API endpoints."""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from .session_store import _get_redis


_requests: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _internal_api_key() -> str:
    return os.environ.get("INTERNAL_API_KEY", "").strip()


def _rate_limit_per_minute() -> int:
    raw = os.environ.get("INTERNAL_API_RATE_LIMIT_PER_MINUTE", "30")
    try:
        return max(1, int(raw))
    except ValueError:
        return 30


def reset_rate_limits() -> None:
    """Clear in-process rate-limit state. Used only by tests."""
    with _lock:
        _requests.clear()


async def require_internal_access(request: Request) -> None:
    """Require a configured shared key and rate-limit protected operations.

    The limiter is deliberately a second line of defence. API-key authentication
    prevents anonymous model-cost abuse; deploy Redis/Cloud Armor for a
    cross-instance global limit when horizontally scaling Cloud Run.
    """
    expected = _internal_api_key()
    supplied = request.headers.get("X-Internal-Api-Key", "")

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API access is not configured",
        )
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )

    client_host = request.client.host if request.client else "unknown"
    bucket = f"{client_host}:{request.url.path}"
    now = time.monotonic()
    cutoff = now - 60.0
    limit = _rate_limit_per_minute()

    redis_client = _get_redis()
    if redis_client is not None:
        # A fixed one-minute Redis bucket provides a shared Cloud Run limit.
        window = int(time.time() // 60)
        redis_key = f"recruiter:rate-limit:{bucket}:{window}"
        try:
            count = int(redis_client.incr(redis_key))
            if count == 1:
                redis_client.expire(redis_key, 60)
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Internal API rate limit exceeded",
                    headers={"Retry-After": "60"},
                )
            return
        except HTTPException:
            raise
        except Exception:
            # Fall back to the in-process limiter if Redis becomes unavailable.
            pass

    with _lock:
        attempts = _requests[bucket]
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Internal API rate limit exceeded",
                headers={"Retry-After": "60"},
            )
        attempts.append(now)
