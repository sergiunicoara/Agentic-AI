"""
Layer 1 Hook: PreToolUse
Intercepts Bash tool calls. When a git commit command is detected,
captures the staged diff and invokes the review pipeline.

Claude Code passes event JSON on stdin:
{
  "tool_name": "Bash",
  "tool_input": {"command": "git commit ..."},
  ...
}
"""
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent


def main() -> None:
    event = json.load(sys.stdin)
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    if tool_name != "Bash":
        return

    command = tool_input.get("command", "")

    # Only intercept actual git commit commands
    if not re.search(r"\bgit\s+commit\b", command):
        return

    # Capture staged diff
    result = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    diff = result.stdout.strip()

    if not diff:
        return  # Nothing staged, let git handle the empty-commit error

    # Invoke the review pipeline asynchronously (non-blocking)
    import asyncio
    import sys as _sys
    _sys.path.insert(0, str(_REPO_ROOT))

    from orchestrator.agent import OrchestratorAgent
    from review_agent.agent import ReviewAgent

    async def _run():
        orchestrator = OrchestratorAgent()
        merged = await orchestrator.run(diff, _REPO_ROOT)
        reviewer = ReviewAgent()
        disposition = await reviewer.review(merged)
        return disposition

    try:
        disposition = asyncio.run(_run())
        verdict = disposition.get("verdict", "comment")
        findings_count = len(disposition.get("findings", []))

        print(f"\n[AIWT] Pre-commit review: {verdict.upper()} — {findings_count} finding(s)")

        if verdict == "request_changes":
            for f in disposition.get("findings", []):
                sev = f.get("severity", "info").upper()
                print(f"  [{sev}] {f.get('file')}:{f.get('line')} — {f.get('message')}")
            # Exit code 1 blocks the commit; output the message
            print("\n[AIWT] Commit blocked: review required. Fix findings or use --no-verify to bypass.")
            sys.exit(1)
    except Exception as e:
        # Never block a commit due to hook failure
        print(f"[AIWT] Hook error (non-blocking): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
