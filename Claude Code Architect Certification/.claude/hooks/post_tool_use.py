"""
CCA-F D1.5: PostToolUse hook — intercept tool RESULTS for transformation/normalization.
Key exam point: PostToolUse hooks can transform results before Claude sees them.
Use for: data normalization, PII scrubbing, result enrichment, latency tracking.
"""
import json
import sys
import os
import re
from datetime import datetime
from time import time


def scrub_pii(text: str) -> str:
    """Remove common PII patterns before results reach Claude's context."""
    # Email
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    # Credit card
    text = re.sub(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[CC_NUMBER]', text)
    # SSN
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
    return text


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = event.get("tool_name", "")
    tool_output = event.get("tool_output", "")
    duration_ms = event.get("duration_ms", 0)
    session_id = event.get("session_id", "unknown")

    # --- Transform 1: PII scrubbing on external data sources ---
    if tool_name in ("mcp__postgres__query", "mcp__filesystem__read_file"):
        if isinstance(tool_output, str):
            tool_output = scrub_pii(tool_output)

    # --- Transform 2: Normalize error shapes from MCP servers ---
    # Ensures Claude always sees the same error structure regardless of server
    if isinstance(tool_output, dict) and tool_output.get("isError"):
        raw_msg = tool_output.get("content", [{}])[0].get("text", "unknown error")
        try:
            parsed = json.loads(raw_msg)
        except (json.JSONDecodeError, TypeError):
            parsed = {"message": raw_msg}

        # Guarantee structured error shape (D2.2)
        tool_output = {
            "isError": True,
            "error_type": parsed.get("error_type", "transient"),
            "message": parsed.get("message", raw_msg),
            "recoverable": parsed.get("recoverable", True),
            "source": tool_name,
            "ts": datetime.utcnow().isoformat(),
        }

    # --- Audit log ---
    os.makedirs(".claude/audit_logs", exist_ok=True)
    with open(".claude/audit_logs/tool_calls.jsonl", "a") as f:
        f.write(json.dumps({
            "ts": datetime.utcnow().isoformat(),
            "hook": "PostToolUse",
            "tool": tool_name,
            "session": session_id,
            "duration_ms": duration_ms,
            "output_type": type(tool_output).__name__,
        }) + "\n")

    # Return (possibly transformed) output
    print(json.dumps({"output": tool_output}))
    sys.exit(0)


if __name__ == "__main__":
    main()
