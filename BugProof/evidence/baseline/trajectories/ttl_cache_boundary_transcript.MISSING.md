# Transcript unrecoverable: ttl_cache_boundary

The raw subagent JSONL transcript for this case's baseline attempt was
copied from the Claude Code task output file
(`tasks/<agent_id>.output`) immediately after the "completed"
notification arrived in the same session that produced it. The copy
came back as 0 bytes; checking the original source file directly
afterward showed it was also 0 bytes at the source, and
`mcp__ccd_session_mgmt__list_sessions` does not list subagents spawned
via the Agent tool as independently queryable sessions -- there is no
other place in this environment to retrieve it from.

The only one of 12 cases where this file survived is
`discount_unit_mismatch_transcript.jsonl` (60,378 bytes) -- most likely
because it was copied earlier in the batch, before whatever retention
window or eviction the harness applies to task output files elapsed for
the rest. This is not a confirmed mechanism, just the most likely
explanation given the evidence.

This was NOT reconstructed, fabricated, or backfilled from
trajectory.md. trajectory.md for this case (agent-authored, not written
by the orchestrating session) remains the available partial record of
what the subagent did. The final CLAIM and candidate_test.py for this
case are unaffected -- they were captured directly from the completion
notification and the workspace directory, not from this transcript file.
