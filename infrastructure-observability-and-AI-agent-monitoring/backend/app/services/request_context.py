"""Request-scoped helpers shared by the REST layer.

Deriving a client IP from ``X-Forwarded-For`` is only safe when the number of
proxies that append to it is known. This app runs behind nginx (which sets the
header from the browser connection) and Envoy (which appends nginx's address),
so the real client sits ``trusted_proxy_hops`` entries from the *right*.
Counting from the right is what makes the value unspoofable: anything a caller
injects is prepended by the chain and can never occupy that position.

A header shorter than the expected chain means the request did not arrive
through it — fall back to the socket peer rather than believing the header.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request

from app.config import settings


def client_ip(request: Request) -> Optional[str]:
    peer = request.client.host if request.client else None

    hops = settings.trusted_proxy_hops
    if hops <= 0:                      # header not trusted at all
        return peer

    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(parts) < hops:              # not the expected proxy chain
        return peer
    return parts[-hops]
