"""
CCA-F D1.5 + D3.x: PreToolUse hook — policy enforcement at the boundary.
Hooks intercept tool calls BEFORE execution for guardrails.
Key exam point: use hooks for policy enforcement, NOT prompt instructions.
Prompt instructions are advisory; hooks are programmatic enforcement (D1.4).
"""
import json
import sys
import os
from datetime import datetime

def main():
    """
    Hook contract: read JSON from stdin, write decision to stdout.
    Exit 0 = allow. Exit 1 = block (message written to stderr shown to Claude).
    """
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # malformed hook input → allow (fail open)

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    session_id = event.get("session_id", "unknown")

    # --- Guardrail 1: Block destructive bash patterns ---
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        blocked_patterns = [
            "DROP TABLE", "TRUNCATE",
            "rm -rf /",
            "pip install",        # enforce uv only
            "sudo rm",
        ]
        for pattern in blocked_patterns:
            if pattern.lower() in command.lower():
                print(json.dumps({
                    "decision": "block",
                    "reason": f"Blocked pattern '{pattern}' in command. Use approved alternatives."
                }))
                sys.exit(1)

    # --- Guardrail 2: Enforce read-only on prod postgres ---
    if tool_name in ("mcp__postgres__query",):
        sql = tool_input.get("sql", "").strip().upper()
        write_ops = ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER")
        if any(sql.startswith(op) for op in write_ops):
            env = os.environ.get("ENV", "prod")
            if env == "prod":
                print(json.dumps({
                    "decision": "block",
                    "reason": "Write operations blocked on prod DB. Use dev/staging."
                }))
                sys.exit(1)

    # --- Audit log: every tool call ---
    log_entry = {
        "ts": datetime.utcnow().isoformat(),
        "hook": "PreToolUse",
        "tool": tool_name,
        "session": session_id,
        "input_keys": list(tool_input.keys()) if isinstance(tool_input, dict) else [],
    }
    os.makedirs(".claude/audit_logs", exist_ok=True)
    with open(".claude/audit_logs/tool_calls.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Allow
    sys.exit(0)


if __name__ == "__main__":
    main()
