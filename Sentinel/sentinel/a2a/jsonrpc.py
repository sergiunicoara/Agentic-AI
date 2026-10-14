"""
JSON-RPC 2.0 envelope handling for the A2A protocol endpoint.

The numeric codes for the A2A-specific errors (TaskNotFoundError and
friends) are assigned here within the -32000..-32099 band that JSON-RPC
2.0 reserves for implementation-defined server errors. The public A2A
spec names these error types but does not appear to mandate one single
canonical numeric assignment — treat these numbers as Sentinel's own,
not as independently verified wire-level conformance with another
implementation.

Wire rules implemented here (JSON-RPC 2.0 §4-§6):
  - A request object with no "id" member is a notification: it is
    executed but gets no response. `"id": null` is NOT a notification
    (it is a request whose id happens to be null), so absence is tracked
    explicitly rather than via a None default.
  - A top-level array is a batch: each element is handled independently,
    responses for notifications are omitted, and an empty array is a
    single Invalid Request error.
  - Sentinel's methods all take named parameters, so `params` must be an
    object when present; anything else is Invalid params (-32602).
  - Internal errors never echo exception text to the caller (it can carry
    file paths, hostnames, or stack details); the detail is logged instead.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

logger = logging.getLogger("sentinel.a2a")


class JsonRpcError(Exception):
    code: int = -32603
    message: str = "Internal error"

    def __init__(self, message: str | None = None, data: Any = None):
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        self.data = data

    def to_dict(self) -> dict:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            body["data"] = self.data
        return body


class ParseError(JsonRpcError):
    code = -32700
    message = "Parse error"


class InvalidRequestError(JsonRpcError):
    code = -32600
    message = "Invalid Request"


class MethodNotFoundError(JsonRpcError):
    code = -32601
    message = "Method not found"


class InvalidParamsError(JsonRpcError):
    code = -32602
    message = "Invalid params"


class InternalError(JsonRpcError):
    code = -32603
    message = "Internal error"


class TaskNotFoundError(JsonRpcError):
    code = -32001
    message = "Task not found"


class TaskNotCancelableError(JsonRpcError):
    code = -32002
    message = "Task cannot be canceled"


class PushNotificationNotSupportedError(JsonRpcError):
    code = -32003
    message = "Push notifications are not supported"


class UnsupportedOperationError(JsonRpcError):
    code = -32004
    message = "Unsupported operation"


class ServerBusyError(JsonRpcError):
    """Too many active tasks on this instance. Sentinel-specific code, chosen
    outside the -32001..-32007 range the A2A spec uses for its own errors."""

    code = -32050
    message = "Server busy: too many active tasks"


class RequestTooLargeError(JsonRpcError):
    code = -32600
    message = "Request body too large"


@dataclass
class JsonRpcRequest:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str | int | float | None = None
    is_notification: bool = False


Handler = Callable[[dict[str, Any]], Awaitable[Any]]


def parse_body(body: bytes) -> tuple[list[Any], bool]:
    """Decode the HTTP body into (raw request items, is_batch).

    Raises ParseError for invalid JSON and InvalidRequestError for an empty
    batch; per-item validation is left to `validate_request` so one bad
    element of a batch doesn't sink the others."""
    try:
        raw = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ParseError() from exc
    if isinstance(raw, list):
        if not raw:
            raise InvalidRequestError("Batch must not be empty")
        return raw, True
    return [raw], False


def _valid_id(value: Any) -> bool:
    # bool is a subclass of int in Python but not a JSON-RPC id type.
    return value is None or (isinstance(value, (str, int, float)) and not isinstance(value, bool))


def request_id_of(raw: Any) -> Any:
    """Best-effort id to echo on an error response for `raw` (null if unusable)."""
    if isinstance(raw, dict) and _valid_id(raw.get("id")):
        return raw.get("id")
    return None


def validate_request(raw: Any) -> JsonRpcRequest:
    """Turn one decoded request object into a JsonRpcRequest, or raise the
    JSON-RPC error that applies to it."""
    if not isinstance(raw, dict) or raw.get("jsonrpc") != "2.0":
        raise InvalidRequestError("Request must be a JSON-RPC 2.0 object")
    method = raw.get("method")
    if not isinstance(method, str) or not method:
        raise InvalidRequestError("Request 'method' must be a non-empty string")
    if "id" in raw and not _valid_id(raw["id"]):
        raise InvalidRequestError("Request 'id' must be a string, number, or null")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise InvalidParamsError("params must be an object (Sentinel methods take named parameters)")
    return JsonRpcRequest(
        method=method,
        params=params,
        id=raw.get("id"),
        is_notification="id" not in raw,
    )


# Kept for callers that handle exactly one request object.
def parse_request(body: bytes) -> JsonRpcRequest:
    items, is_batch = parse_body(body)
    if is_batch:
        raise InvalidRequestError("Batch requests are not accepted here")
    return validate_request(items[0])


def success_response(request_id: str | int | None, result: Any) -> dict:
    payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def error_response(request_id: str | int | None, error: JsonRpcError) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": error.to_dict()}


def internal_error(exc: BaseException, context: str) -> InternalError:
    """Log `exc` with its traceback and return a generic InternalError that
    reveals nothing about it to the caller."""
    logger.error("a2a.internal_error context=%s", context, exc_info=exc)
    return InternalError()


async def dispatch(request: JsonRpcRequest, handlers: dict[str, Handler]) -> dict:
    """Look up and invoke the handler for `request.method`, wrapping the result
    (or any raised JsonRpcError) in a JSON-RPC response envelope. The caller
    decides whether to send it (it must not for a notification)."""
    handler = handlers.get(request.method)
    if handler is None:
        return error_response(request.id, MethodNotFoundError(f"Unknown method: {request.method}"))

    try:
        result = await handler(request.params)
        return success_response(request.id, result)
    except JsonRpcError as exc:
        return error_response(request.id, exc)
    except Exception as exc:  # noqa: BLE001 - convert any handler bug into a valid envelope
        return error_response(request.id, internal_error(exc, request.method))
