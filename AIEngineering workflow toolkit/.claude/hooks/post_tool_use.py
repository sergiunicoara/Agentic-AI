"""
Layer 1 Hook: PostToolUse
Intercepts Write/Edit/MultiEdit tool completions. Extracts the changed file path,
generates a single-file diff, and:
  1. POSTs directly to the running AIWT web server (if localhost:8000 is up)
  2. Falls back to the file queue (.claude/review_queue.jsonl)

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
import urllib.request
import urllib.error
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_REVIEW_QUEUE = _REPO_ROOT / ".claude" / "review_queue.jsonl"
_AIWT_API = "http://localhost:8000"


def _post_to_api(diff: str, file_path: str) -> bool:
    """
    Try to POST the diff directly to the running AIWT web server.
    Returns True on success, False if server is not reachable.
    Uses stdlib only — no third-party imports.
    """
    try:
        title = f"Hook: {Path(file_path).name}"
        payload = json.dumps({
            "diff": diff,
            "title": title,
            "source": "hook",
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{_AIWT_API}/api/reviews",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            review_id = data.get("id", "")
            print(
                f"[AIWT] ✓ Live review started → "
                f"{_AIWT_API}/reviews/{review_id}  ({Path(file_path).name})"
            )
            return True
    except (urllib.error.URLError, OSError):
        return False  # Server not running — fall through to file queue
    except Exception as e:
        print(f"[AIWT] API post error (non-blocking): {e}", file=sys.stderr)
        return False


def _queue_to_file(diff: str, file_path: str) -> None:
    """Fall-back: append to the file queue for later processing."""
    entry = {"file": str(file_path), "diff": diff}
    with open(_REVIEW_QUEUE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[AIWT] Queued review for {Path(file_path).name} (server offline)")


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
            rel = (
                abs_path.relative_to(_REPO_ROOT)
                if abs_path.is_relative_to(_REPO_ROOT)
                else abs_path
            )
            diff_lines = [f"+++ b/{rel}"]
            diff_lines += [f"+{line}" for line in content.splitlines()]
            diff = "\n".join(diff_lines)

        if not diff:
            return

        # Try live API first; fall back to queue
        posted = _post_to_api(diff, str(abs_path))
        if not posted:
            _queue_to_file(diff, str(abs_path))

    except Exception as e:
        print(f"[AIWT] Hook error (non-blocking): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
