# Why this directory is empty

BUGPROOF_AGENT_BRIEF.md's cassette design assumes raw LLM API calls: record
each request/response pair, hash-key them, replay by matching a new
request's hash against a recorded one. That requires a raw provider API
key. None was available in this environment for Claude (Claude Code itself
authenticates via OAuth, not a key this process can hand to a separate SDK
client), and using the OpenAI/Google keys present in the environment for
this purpose was declined — see `src/bugproof/baseline.py`'s module
docstring and `evidence/baseline/config.json` for the full reasoning.

The actual offline-replayable artifacts for Phase 2 live in
`evidence/baseline/trajectories/` and `evidence/baseline/candidates/` (the
frozen final test file per case). A judge reproduces the headline
VRR/FCRR numbers by running `python eval/run_baseline_replay.py`, which
re-evaluates the frozen candidates through the unmodified deterministic
oracle — no LLM call, no API key, no network. What isn't
offline-replayable is regenerating the candidates themselves from
scratch, since that requires either a live agent session or a provided
API key.

**Known evidence limitation, disclosed rather than implied away:** only
**1 of 12 cases** (`discount_unit_mismatch`) has a recoverable raw
subagent JSONL transcript (`discount_unit_mismatch_transcript.jsonl`,
60,378 bytes). The other 11 came back 0 bytes even at the Claude Code
task-output source, not just in this session's copies, and are marked
`*_transcript.MISSING.md` in `evidence/baseline/trajectories/` rather
than fabricated or reconstructed. This was investigated (checked the
source files directly, checked whether subagents are queryable as
separate sessions — they aren't) before concluding it was unrecoverable
in this environment, and the human explicitly decided against rerunning
the baseline to regenerate them, since that would create a new sample and
invalidate the frozen timing/token/result evidence. Every case does still
have a structured `trajectory.md` (agent-authored, written as part of the
task itself) and its frozen `candidate_test.py` — those are unaffected
and complete for all 12 cases; it is specifically the raw transcript that
is missing for 11 of them.
