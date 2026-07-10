"""Starlette middleware that records every non-GET, non-OPTIONS request
to the audit_logs table after the response is sent."""

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.db import AsyncSessionLocal
from app.models.user import AuditLog
from app.services.auth_service import decode_token


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Only log mutating requests
        if request.method in ("GET", "OPTIONS", "HEAD"):
            return response

        user_id = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                payload = decode_token(auth.split(" ", 1)[1])
                user_id = payload.get("sub")
            except Exception:
                pass

        ip = request.headers.get("x-forwarded-for") or (
            request.client.host if request.client else None
        )

        async with AsyncSessionLocal() as db:
            db.add(
                AuditLog(
                    user_id=user_id,
                    method=request.method,
                    path=str(request.url.path),
                    status_code=response.status_code,
                    ip_address=ip,
                    user_agent=request.headers.get("user-agent"),
                )
            )
            await db.commit()

        return response
