# Audit remediation plan

Source: three-way audit (A2A layer, pipeline/agents/mcp/redteam, tests/docs). Card fixes already landed
(`agent_card.py`, `check_deployment_config`, `tests/test_a2a.py`).

Design decisions taken (user said "implement all"; revisit any of these):
- Signing: HMAC-SHA256 over canonical attestation JSON, key from `SENTINEL_SIGNING_KEY`. Unset key => signature is
  the literal string `unsigned`, never a random id that looks signed. `verify_attestation()` added.
- Evidence gate: evidence store stays server-side; a finding survives only if EVERY cited id exists and the
  cited evidence matches the finding (same pillar/source family and file, where the finding names one).
- pip-audit / live red-team: hardening only (no container). Unpinned target requirements => inconclusive, not run.
- Fail closed: a scanner that is missing, times out or errors makes the verdict `inconclusive`, never `pass`.

## Track 1 — pipeline, agents, mcp, redteam (one owner; shared files)
- [ ] Resolve scanner executables via the running interpreter's Scripts/bin dir, then `shutil.which`
- [ ] Evidence carries tool status; missing/timeout/rc-error => `inconclusive` verdict; CLI exits non-zero
- [ ] `_validate_target` once at top of `run_sentinel`; pass resolved Path to skills/redteam/llm_auditor
- [ ] Relative paths resolve against SCAN_ROOT everywhere
- [ ] Parse current pip-audit JSON (`{"dependencies": [...]}`), map PYSEC/GHSA/CVE severity sanely,
      no requirements.txt => inconclusive (never audit Sentinel's own env)
- [ ] pip-audit on target reqs: only pinned/hashed, `--no-deps --disable-pip`; else inconclusive
- [ ] bandit: own config, `--ignore-nosec`; semgrep: `--disable-nosem`; ignore target-supplied `.bandit`
- [ ] Always run every deterministic auditor (drop skill-gating of auditors)
- [ ] semgrep: one error must not discard a config group's results; per-call registry-pack flag
- [ ] Signing: HMAC + `verify_attestation`; README/agent-prompt wording matches reality
- [ ] Gate: every cited id valid AND evidence matches finding; `produce_attestation` uses server-side store
- [ ] Adjudicator: tolerate non-dict candidates, don't mutate input; SARIF real file locations
- [ ] Live red-team: temp cwd, scrubbed env, process-group kill, LIVE-CONFIRMED needs observed effect
- [ ] Tests for each of the above (fail-closed with empty PATH, outside-root target, pip-audit format, gate,
      signature verify/tamper)

## Track 2 — A2A layer (sentinel/a2a/*, tests/test_a2a*.py)
- [ ] `/ws/scan`: token + Origin check before accept, concurrency semaphore, cancel on disconnect
- [ ] SSE: unsubscribe in `finally`, drop task entry on final event, subscribe-before-read in resubscribe,
      heartbeat polls store for terminal state, max stream lifetime
- [ ] Compare-and-swap state transition in both stores; publish final only when CAS wins
- [ ] Dedicated bounded ThreadPoolExecutor + admission semaphore; `.result(timeout=...)`
- [ ] SSE frames as JSON-RPC responses with TaskStatusUpdateEvent / TaskArtifactUpdateEvent (`kind`, `contextId`)
- [ ] JSON-RPC: notifications get no response, batch support, -32602 for bad params, no internal-error leaks,
      streaming-path errors map correctly
- [ ] Body size cap, metadata key allow-list, per-caller task cap
- [ ] Redis NX/GET expiry race; `historyLength` edge cases; keep refs to background tasks
- [ ] Tests: every route x token present/absent/wrong, CAS race with fakeredis, SSE cleanup

## Track 3 — deploy, docs, config (after Tracks 1-2)
- [ ] `K_SERVICE` => require token at startup; `deploy.sh` sets token secret + public URL, pinned image tag
- [ ] Dockerfile: non-root USER, no test tools in prod image, `.dockerignore` additions
- [ ] Pin deps (lock file)
- [ ] README: test count, runtime, config/env-var table, `/ws/scan` auth, accurate signing/gate claims
- [ ] CLAUDE.md: real commands (venv, scanners on PATH)
- [ ] tests: `test_eval` T3 asserts `fail`, scanner-availability session fixture

## Review
**Status (2026-10-14):** all three tracks landed in the working tree, uncommitted. Full suite: 141 passed,
4 skipped (semgrep, unavailable on native Windows), with and without the venv on PATH.

Verified by re-running the original failures: a target outside SCAN_ROOT and a missing scanner both return
`inconclusive` (previously `pass`, exit 0).

**Not verified / open**
- semgrep paths were never exercised (not installable here) — run the suite on Linux/CI before trusting them.
- Track 1 and 2 agents were cut off by a usage limit before their final reports; I checked their checklist items
  against the code (CAS `transition`, limits, body cap, Origin/token on /ws/scan, SSE unsubscribe, pinned-only
  pip-audit, nosec/nosem disabling, always-on auditors) but did not line-review every diff.
- `deploy/deploy.sh` passes `bash -n` only; never run against GCP. Needs the two Secret Manager secrets first.
- Live red-team is hardened (temp cwd, scrubbed env, process-group kill, sink-based confirmation), NOT isolated —
  no container/seccomp. pip-audit is restricted to pinned requirements, not sandboxed.
- Gate matching rules (finding-to-evidence) are a first cut; review `adjudicator.py` before relying on them.
- Dashboard change (token from `/ui/?token=`) is source-only; `dist/` not rebuilt.
- Image digests not pinned; no lockfile with hashes.

**Lesson:** parallel agents on a rate-limited plan can die mid-task with no report — keep the plan file current so
state is recoverable from disk.

