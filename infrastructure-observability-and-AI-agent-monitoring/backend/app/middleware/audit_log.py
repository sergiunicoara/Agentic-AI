"""Starlette middleware that records every mutating request to the audit_logs
table after the response is produced."""

import logging
from typing import Callable

from fastapi import Request, Response
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.db import AsyncSessionLocal
from app.models.user import AuditLog
from app.services.auth_service import decode_token
from app.services.request_context import client_ip

logger = logging.getLogger(__name__)


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Only log mutating requests
        if request.method in ("GET", "OPTIONS", "HEAD"):
            return response

        try:
            await self._record(request, response)
        except Exception:
            # The request itself already succeeded. A logging failure must not
            # convert it into a 500 — surface it in the logs instead, where the
            # gap in the audit trail is visible.
            logger.exception(
                "Failed to write audit log for %s %s", request.method, request.url.path
            )

        return response

    @staticmethod
    async def _record(request: Request, response: Response) -> None:
        user_id = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                user_id = decode_token(auth.split(" ", 1)[1]).get("sub")
            except JWTError:
                pass  # unauthenticated / invalid token — still worth logging

        async with AsyncSessionLocal() as db:
            db.add(
                AuditLog(
                    user_id=user_id,
                    method=request.method,
                    path=str(request.url.path),
                    status_code=response.status_code,
                    ip_address=client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
            )
            await db.commit()
