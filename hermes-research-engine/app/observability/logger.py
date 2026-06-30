import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """JSON-lines logger with trace_id, agent_id, token tracking."""

    def __init__(self, log_file: str = "data/agent.log"):
        self.log_file = log_file

    def _write(self, record: dict) -> None:
        record["ts"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(record)
        print(line)
        try:
            with open(self.log_file, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def step(
        self,
        trace_id: str,
        agent_id: str,
        event: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        **extra: Any,
    ) -> None:
        self._write(
            {
                "trace_id": trace_id,
                "agent_id": agent_id,
                "event": event,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": round(latency_ms, 2),
                **extra,
            }
        )

    def tool_call(self, trace_id: str, agent_id: str, tool: str, args: dict, result_len: int) -> None:
        self._write(
            {
                "trace_id": trace_id,
                "agent_id": agent_id,
                "event": "tool_call",
                "tool": tool,
                "args": args,
                "result_len": result_len,
            }
        )

    def error(self, trace_id: str, agent_id: str, msg: str, **extra: Any) -> None:
        self._write({"trace_id": trace_id, "agent_id": agent_id, "event": "error", "msg": msg, **extra})


logger = StructuredLogger()
