"""AgentTracer: top-level entry point for SDK users."""

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from agent_observability.emitter import AsyncGrpcEmitter
from agent_observability.otel_bridge import OtelBridge
from agent_observability.span import AsyncSpan


class AgentTrace:
    """Represents one end-to-end task trace.  Created via AgentTracer.trace()."""

    def __init__(
        self,
        tracer: "AgentTracer",
        task_id: str,
        trace_id: Optional[str] = None,
    ):
        self._tracer = tracer
        self.task_id = task_id
        self.trace_id = trace_id or str(uuid.uuid4())
        self._outcome = "pending"

    @asynccontextmanager
    async def span(
        self,
        event_type: str,
        model: str = "",
        parent_span_id: str = "",
    ) -> AsyncGenerator[AsyncSpan, None]:
        s = AsyncSpan(self, event_type, model=model, parent_span_id=parent_span_id)
        with self._tracer._otel.span(event_type, attributes={"trace_id": self.trace_id}):
            async with s:
                yield s

    def set_outcome(self, outcome: str) -> None:
        """Call before the trace context exits to record final outcome."""
        self._outcome = outcome

    async def _emit(self, **kwargs) -> None:
        await self._tracer._emitter.emit(
            trace_id=self.trace_id,
            agent_name=self._tracer.agent_name,
            task_id=self.task_id,
            outcome=self._outcome,
            **kwargs,
        )

    async def __aenter__(self) -> "AgentTrace":
        await self._emit(
            span_id=str(uuid.uuid4()),
            event_type="span_start",
            timestamp_ms=int(time.time() * 1000),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, _tb) -> None:
        if exc_type is not None and self._outcome == "pending":
            self._outcome = "failure"
        elif self._outcome == "pending":
            self._outcome = "success"

        await self._emit(
            span_id=str(uuid.uuid4()),
            event_type="span_end",
            timestamp_ms=int(time.time() * 1000),
        )


class AgentTracer:
    """
    Top-level tracer.  Connects to the gRPC backend once and provides
    trace() and span() context managers for instrumentation.

    Usage::

        tracer = AgentTracer(server="localhost:50051", agent_name="my-agent")

        async with tracer:
            async with tracer.trace("task-001") as trace:
                async with trace.span("llm_call", model="claude-sonnet-4-6") as span:
                    result = await call_llm(prompt)
                    span.record_tokens(input=512, output=128)
    """

    def __init__(
        self,
        server: str = "localhost:50051",
        agent_name: str = "unnamed-agent",
        service_name: str = "agent-sdk",
    ):
        self.agent_name = agent_name
        self._emitter = AsyncGrpcEmitter(server)
        self._otel = OtelBridge(service_name)

    @asynccontextmanager
    async def trace(
        self,
        task_id: str,
        trace_id: Optional[str] = None,
    ) -> AsyncGenerator[AgentTrace, None]:
        t = AgentTrace(self, task_id, trace_id=trace_id)
        async with t:
            yield t

    async def __aenter__(self) -> "AgentTracer":
        await self._emitter.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self._emitter.close()
