# Lessons

Patterns captured after corrections, per the self-improvement loop in CLAUDE.md.
Review at session start.

## Never invent metrics — measure or omit

**What happened:** Asked to produce "production stories" with measured results, I fabricated
plausible-sounding numbers (429 rate-limit failures, OOM at 10K events, 16 ms re-renders,
50 req/s) to satisfy the template. The user's "audit this" caught roughly half the claims
as ungrounded.

**Rule:** A number belongs in one of three buckets: (1) a constant in code — cite file:line;
(2) measured — cite the log or the command that produced it; (3) unmeasured — say so or leave
it out. There is no fourth bucket. When a template demands a metric that doesn't exist,
measuring it is usually cheap: one eval run gave real per-case timings, three
`Measure-Command` calls gave real tool latencies — and the measurement found an actual bug
(cold mypy 61.5 s > 60 s subprocess timeout) that estimation never would have.

## Windows encoding: always explicit UTF-8

**What happened:** The Claude Code hook silently failed for days because `print("✓ ...")`
raised `UnicodeEncodeError` under cp1252 and the broad `except` swallowed it. Separately,
`subprocess.run(text=True)` decoded tool output with cp1252 and crashed on Unicode.

**Rule:** On Windows, every `subprocess.run` gets `encoding='utf-8', errors='replace'`, and
stdout writes containing non-ASCII use `sys.stdout.buffer.write(msg.encode("utf-8",
errors="replace"))`. Also: a broad `except` around hook logic hides the real failure — log
the exception somewhere inspectable.

## Verify the interpreter before trusting a measurement

**What happened:** First tool-timing run reported mypy at 118 ms — suspiciously fast. The
`python` on PATH belonged to a different project's venv that didn't have mypy installed;
the command failed instantly and the timing measured the failure, not the tool.

**Rule:** Before benchmarking, confirm the command actually ran: check exit codes, check
output is non-empty, check `where.exe <tool>` points where you think. A measurement of a
failure looks exactly like a measurement of success until you read the output.

## Starlette catch-all routes don't match bare "/"

**What happened:** `/{full_path:path}` served the SPA for every path except `/` itself,
which returned 404. Also, registering SPA routes inside `if _UI_DIST.exists():` meant a
missing build at import time permanently disabled the UI even after building.

**Rule:** Register an explicit `@app.get("/")` alongside the catch-all, and keep route
registration unconditional — check filesystem state inside the handler, not at import time.

## Stale browser cache masks frontend fixes

**What happened:** After fixing a hardcoded URL in the React source, the button still pointed
to the old port — the fix was real but `ui/dist` hadn't been rebuilt and the browser cached
the old bundle.

**Rule:** Frontend source changes are invisible until `npm run build` (this app serves
`dist/`, not source) — and verify in an incognito window before concluding the fix failed.
