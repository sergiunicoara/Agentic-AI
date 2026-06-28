# Sentinel Security & Red-Team Evaluation Harness
import sys as _sys

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
