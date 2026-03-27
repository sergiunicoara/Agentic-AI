"""
Layer 1 Hook: PostToolUse
Intercepts Write/Edit/MultiEdit tool completions. Extracts the changed file path,
generates a single-file diff, and queues it for review.

Claude Code passes event JSON on stdin:
{
  "tool_name": "Write",
  "tool_input": {"file_path": "...", "content": "..."},
  "tool_response": {...}
}
"""
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_REVIEW_QUEUE = _REPO_ROOT / ".claude" / "review_queue.jsonl"


def main() -> None:
    event = json.load(sys.stdin)
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return

    # Extract file path
    file_path = tool_input.get("file_path") or tool_input.get("path")
    if not file_path:
        return

    abs_path = Path(file_path)
    if not abs_path.exists():
        return

    # Skip non-code files (docs, config, binary)
    skip_extensions = {".md", ".json", ".yaml", ".yml", ".toml", ".lock", ".txt"}
    if abs_path.suffix.lower() in skip_extensions:
        return

    # Generate diff against git HEAD (or full file if untracked)
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", str(abs_path)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        diff = result.stdout.strip()

        if not diff:
            # Untracked file — treat entire content as a diff
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            rel = abs_path.relative_to(_REPO_ROOT) if abs_path.is_relative_to(_REPO_ROOT) else abs_path
            diff_lines = [f"+++ b/{rel}"]
            diff_lines += [f"+{line}" for line in content.splitlines()]
            diff = "\n".join(diff_lines)

        if not diff:
            return

        # Append to review queue (processed by background worker or CLI)
        entry = {"file": str(abs_path), "diff": diff}
        with open(_REVIEW_QUEUE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        print(f"[AIWT] Queued review for {abs_path.name}")

    except Exception as e:
        print(f"[AIWT] Hook error (non-blocking): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
