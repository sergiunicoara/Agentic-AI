"""Async context manager representing a single observability span."""

import time
import uuid
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agent_observability.tracer import AgentTrace


class AsyncSpan:
    def __init__(
        self,
        trace: "AgentTrace",
        event_type: str,
        model: str = "",
        parent_span_id: str = "",
    ):
        self._trace = trace
        self.span_id = str(uuid.uuid4())
        self.event_type = event_type
        self.model = model
        self.parent_span_id = parent_span_id
        self._start_ms: int = 0

        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._attributes: dict[str, str] = {}
        self._status: str = "ok"
        self._error: str = ""

    def record_tokens(self, *, input: int = 0, output: int = 0) -> None:
        self._input_tokens += input
        self._output_tokens += output

    def set_attribute(self, key: str, value: str) -> None:
        self._attributes[key] = value

    def set_error(self, message: str) -> None:
        self._status = "error"
        self._error = message

    async def __aenter__(self) -> "AsyncSpan":
        self._start_ms = int(time.time() * 1000)
        await self._trace._emit(
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            event_type="span_start",
            timestamp_ms=self._start_ms,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, _tb) -> None:
        end_ms = int(time.time() * 1000)
        if exc_type is not None:
            self._status = "error"
            self._error = str(exc_val)

        await self._trace._emit(
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            event_type=self.event_type,
            timestamp_ms=self._start_ms,
            duration_ms=end_ms - self._start_ms,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            model=self.model,
            status=self._status,
            error_message=self._error,
            attributes=self._attributes,
        )
