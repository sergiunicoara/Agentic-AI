# Episode 2 — `roster_lookup_wrong_exception`: execution failure caught, repair fully fixes it

**Demonstrates:** the mechanical execution gate catching an agent
contradicting its own passing test output (not the evidence gate), and
the bounded repair fully resolving what was a Phase 2 failure — this
episode's D outcome is the one clean full fix in the whole D batch.

## Source artifacts (original, unmodified)

| Path | SHA-256 |
|---|---|
| `cases/roster_lookup_wrong_exception/report.md` | `483cd5ab00e44ffd8c22bf42ea51477ff138037e37017b4652973ec94927d4f3` |
| `evidence/advanced/trajectories/roster_lookup_wrong_exception/bundle.json` | `244e8354e8da84b01cead5da1e4d6e58568f85a28956806def8eb9e472d915cd` |
| `evidence/advanced/candidates/C/roster_lookup_wrong_exception/candidate_test.py` | `f985ad23017a1ac2f249abfcfae4fe4259a2cdc08cf0f52adbaf58646853c017` |
| `evidence/advanced/candidates/D/roster_lookup_wrong_exception/candidate_test.py` | `89026e74a22e879612f1a1ba8ade4ecc7f56b72168398726d0405d1d22707c21` |

## Input — bug report (directly captured, verbatim)

> A support ticket came in saying that looking up a specific member by id
> sometimes throws an unhandled error and the request fails hard instead
> of giving a normal "member not found" response. It only happens for ids
> that don't exist in the current roster — looking up ids that do exist
> works fine. The error in the logs was `IndexError: list index out of
> range`.

## Round C — generation

**Final candidate:** asserted `pytest.raises(IndexError)` around the
missing-id lookup — i.e. asserted the *current buggy behavior itself* as
correct, rather than the desired replacement behavior.

**Execution outcome (orchestrator-measured):** `EXECUTION_FAILURE /
NO_FAILURE_OBSERVED` — "candidate collected and passed on buggy/ -- no
failure to reproduce." The agent's own self-reported `trajectory.md` said
the test **PASSED**, in the same breath as claiming reproduction — the
orchestrator's independent re-execution is what caught this, not the
Evidence Gate (the exception contract was, in fact, correctly grounded:
`'IndexError': GROUNDED -- grounded by literal item
'missing-id-indexerror'`).

**Oracle measurement (separate, later):** `REJECTED / PASSES_ON_BUGGY` —
independently confirms the same fact the execution gate already caught.

## Round D — bounded repair (fired: `EXECUTION_FAILURE` triggers it)

**Repair prompt (directly captured):** included the orchestrator's real
execution result (`status=EXECUTION_FAILURE reason=NO_FAILURE_OBSERVED`)
and an explicit note that `pytest.raises(IndexError)` around code that
already raises `IndexError` is success, not failure, for pytest — asking
the agent to assert the *desired* behavior instead.

**Repaired candidate:** rewrote the missing-id assertion as `try:
find_member(...); except IndexError: pytest.fail(...)` — asserting only
that a raw, unhandled `IndexError` does *not* occur, without guessing a
specific replacement exception the report never states.

**Execution outcome:** re-run genuinely fails on `buggy/` — `1 failed, 1
passed`, the failing test's traceback showing `IndexError: list index out
of range` raised from `roster.py:4`, exactly the reported defect.

**Gate/claim outcome:** Evidence Gate `SUPPORTED` (no exact-value contract
remains after narrowing — `pytest.raises` was replaced by a `try/except`
pattern with no `==`/`is`/`raises(...)` comparison for the extractor to
find). Final claim: `VERIFIED_REPRODUCTION`.

**Oracle measurement:** `VALID` — all five conditions satisfied. **This
Phase 2 failure case is fully resolved by D.**

## Agent self-reported (not independently re-verified beyond execution results above)

Both C and D's `trajectory.md` report copying the candidate into `buggy/`,
running it once, observing the result, then removing the temp copy and
pytest-generated cache directories, restoring `buggy/roster.py` to its
original state — confirmed unmodified by the orchestrator's own
byte-for-byte diff (`buggy_tampering_detected: false` in both rounds'
`execution_result`).

## Human checkpoint / orchestration decision

All 8 repair calls in this batch (including this one) were verified
through the same pipeline (execution → contract extraction → evidence
parsing → grounding → claim → oracle measurement) together, after all 8
had completed — not via a per-repair live checkpoint. `empty_list_average_crash`,
not this case, was the first repair notification to actually arrive; no
distinct inline checkpoint was performed for this specific case beyond
that shared batch verification pass.
