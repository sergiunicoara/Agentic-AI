# Sentinel Security & Red-Team Evaluation Harness
import os as _os
import sys as _sys
from pathlib import Path as _Path

# Several modules print human-readable report glyphs (✓ ✗ etc.). On Windows
# the default console encoding is cp1252, which raises UnicodeEncodeError on
# those characters. Reconfigure stdout/stderr to utf-8 once, here, so it
# applies no matter which entry point runs first — the full pipeline, a
# single agent tool (e.g. the Attestation agent calling adjudicate()
# directly), the eval runner, the A2A server, or pytest.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _load_local_env_file() -> None:
    """Load repo-local .env settings for local CLI runs.

    This keeps commands like `python -m sentinel.eval.llm_gate_report`
    working from a plain terminal without requiring the user to export
    environment variables manually.
    """
    env_path = _Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in _os.environ:
                _os.environ[key] = value
    except OSError:
        pass


_load_local_env_file()
