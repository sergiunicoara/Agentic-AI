"""
CCA-F D2.2: Structured Error Responses from MCP Servers
The isError flag pattern — all MCP tools must use this, not raise exceptions.

Error categories (exam critical):
- transient:    network/timeout — recoverable, include retry_after
- validation:   bad input — recoverable=False, include expected_format
- business:     policy violation — recoverable=False, escalate=True
- permission:   auth failure — recoverable=False, escalate=True
"""
from __future__ import annotations
import json
from dataclasses import dataclass


@dataclass
class MCPError:
    """Standard error shape for all MCP tool responses."""
    error_type: str      # transient | validation | business | permission
    message: str
    recoverable: bool
    retry_after: int = 0          # seconds; only for transient
    expected_format: str = ""     # only for validation errors
    escalate: bool = False        # True for business/permission errors
    source: str = ""              # which MCP server produced this
    context: dict = None          # additional debugging context

    def __post_init__(self):
        if self.context is None:
            self.context = {}

    def to_tool_result(self) -> dict:
        """
        D2.2: Return in MCP isError format.
        Claude sees this as a structured error, not an exception.
        """
        payload = {
            "error_type": self.error_type,
            "message": self.message,
            "recoverable": self.recoverable,
            "source": self.source,
        }
        if self.retry_after:
            payload["retry_after"] = self.retry_after
        if self.expected_format:
            payload["expected_format"] = self.expected_format
        if self.escalate:
            payload["escalate"] = True
        if self.context:
            payload["context"] = self.context

        return {
            "isError": True,
            "content": [{"type": "text", "text": json.dumps(payload)}]
        }


# --- Factory functions for each error type ---

def transient_error(message: str, source: str, retry_after: int = 5) -> dict:
    """Network/timeout errors — Claude should retry after delay."""
    return MCPError(
        error_type="transient",
        message=message,
        recoverable=True,
        retry_after=retry_after,
        source=source,
    ).to_tool_result()


def validation_error(message: str, source: str, expected_format: str) -> dict:
    """Bad input — don't retry, fix the input."""
    return MCPError(
        error_type="validation",
        message=message,
        recoverable=False,
        expected_format=expected_format,
        source=source,
    ).to_tool_result()


def permission_error(message: str, source: str) -> dict:
    """Auth failure — escalate to human."""
    return MCPError(
        error_type="permission",
        message=message,
        recoverable=False,
        escalate=True,
        source=source,
    ).to_tool_result()


def business_error(message: str, source: str, context: dict | None = None) -> dict:
    """Policy violation — escalate to human."""
    return MCPError(
        error_type="business",
        message=message,
        recoverable=False,
        escalate=True,
        source=source,
        context=context or {},
    ).to_tool_result()
