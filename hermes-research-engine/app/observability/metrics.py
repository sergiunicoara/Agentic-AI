import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RequestMetrics:
    trace_id: str
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    agent_calls: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    total_latency_ms: float = 0.0
    _start: float = field(default_factory=time.perf_counter, repr=False)

    def add_llm(self, tokens_in: int, tokens_out: int, latency_ms: float) -> None:
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.total_latency_ms += latency_ms
        self.llm_calls += 1

    def add_tool(self) -> None:
        self.tool_calls += 1

    def to_headers(self) -> Dict[str, str]:
        return {
            "X-Trace-Id": self.trace_id,
            "X-Tokens-In": str(self.total_tokens_in),
            "X-Tokens-Out": str(self.total_tokens_out),
            "X-LLM-Calls": str(self.llm_calls),
            "X-Tool-Calls": str(self.tool_calls),
            "X-Total-Latency-Ms": str(round(self.total_latency_ms, 1)),
        }

    def summary(self) -> dict:
        elapsed = round((time.perf_counter() - self._start) * 1000, 1)
        return {
            "trace_id": self.trace_id,
            "tokens_in": self.total_tokens_in,
            "tokens_out": self.total_tokens_out,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "wall_ms": elapsed,
        }
