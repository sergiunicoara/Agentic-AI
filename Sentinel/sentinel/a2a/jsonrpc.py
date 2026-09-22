"""
JSON-RPC 2.0 envelope handling for the A2A protocol endpoint.

The numeric codes for the A2A-specific errors (TaskNotFoundError and
friends) are assigned here within the -32000..-32099 band that JSON-RPC
2.0 reserves for implementation-defined server errors. The public A2A
spec names these error types but does not appear to mandate one single
canonical numeric assignment — treat these numbers as Sentinel's own,
not as independently verified wire-level conformance with another
implementation.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError


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


class JsonRpcRequest(BaseModel):
    jsonrpc: str
    method: str
    params: dict[str, Any] = {}
    id: str | int | None = None


Handler = Callable[[dict[str, Any]], Awaitable[Any]]


def parse_request(body: bytes) -> JsonRpcRequest:
    import json

    try:
        raw = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ParseError(str(exc)) from exc

    if not isinstance(raw, dict) or raw.get("jsonrpc") != "2.0" or "method" not in raw:
        raise InvalidRequestError("Request must be a JSON-RPC 2.0 object with a 'method'")

    try:
        return JsonRpcRequest.model_validate(raw)
    except ValidationError as exc:
        raise InvalidRequestError(str(exc)) from exc


def success_response(request_id: str | int | None, result: Any) -> dict:
    payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def error_response(request_id: str | int | None, error: JsonRpcError) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": error.to_dict()}


async def dispatch(request: JsonRpcRequest, handlers: dict[str, Handler]) -> dict:
    """Look up and invoke the handler for `request.method`, wrapping the result
    (or any raised JsonRpcError) in a JSON-RPC response envelope."""
    handler = handlers.get(request.method)
    if handler is None:
        return error_response(request.id, MethodNotFoundError(f"Unknown method: {request.method}"))

    try:
        result = await handler(request.params)
        return success_response(request.id, result)
    except JsonRpcError as exc:
        return error_response(request.id, exc)
    except Exception as exc:  # noqa: BLE001 - convert any handler bug into a valid envelope
        return error_response(request.id, InternalError(str(exc)))
