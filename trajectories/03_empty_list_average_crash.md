# Episode 3 — `empty_list_average_crash`: repair reaches oracle-VALID, system still abstains

**Demonstrates:** "abstention is not free" concretely. Repair genuinely
fixed the underlying test logic — the repaired candidate is oracle-`VALID`
— but the system's own final claim is `INSUFFICIENT_EVIDENCE`, purely
because of a format-compliance failure in where the EVIDENCE block was
written, not because the reasoning was weak.

## Source artifacts (original, unmodified)

| Path | SHA-256 |
|---|---|
| `cases/empty_list_average_crash/report.md` | `bfdcfc1ca2c2a975416819d5057f65132157bebe133fa9de24b2079de1fe21bd` |
| `evidence/advanced/trajectories/empty_list_average_crash/bundle.json` | `0e1d32f8dd895eb3afce054e24b454e343313040bb6769c358354235be680222` |
| `evidence/advanced/candidates/C/empty_list_average_crash/candidate_test.py` | `d50eae2b2828e82b9126f202fded3f26e12e84bb5b227a24db00b3bc3c853a29` |
| `evidence/advanced/candidates/D/empty_list_average_crash/candidate_test.py` | `33cebe0052fb468451f0729e77b54dd5fcc1747b9a0353c02869f4eec4f24124` |

## Input — bug report (directly captured, verbatim)

> Got a crash report from someone who'd just created a new quiz and
> hadn't had anyone take it yet. Stack trace points into the stats helper
> somewhere, ZeroDivisionError. My guess is it's trying to average scores
> before any exist.

## Round C — generation

**Final candidate:** `pytest.raises(ZeroDivisionError)` around
`average_score([])` — asserting the current buggy crash itself as the
expected outcome.

**Execution outcome (orchestrator-measured):** `EXECUTION_FAILURE /
NO_FAILURE_OBSERVED` — the test passes on `buggy/` (the expected exception
is exactly what's raised, so `pytest.raises` reports success). The agent's
own self-reported `trajectory.md` literally recorded `PASSED [100%]` in
the same breath as claiming `VERIFIED_REPRODUCTION`.

**Oracle measurement:** `REJECTED / PASSES_ON_BUGGY` — independently
confirms the same fact.

## Round D — bounded repair (fired: `EXECUTION_FAILURE` triggers it)

**Repaired candidate:** rewrote the test to call `average_score([])` as a
bare statement, no `pytest.raises` guard — the exception now genuinely
propagates and fails the test on `buggy/`. The agent explicitly declined
to pin a replacement return value: *"report.md never states what the
fixed function should return instead... I narrowed the assertion to only
what report.md actually supports: that calling `average_score` on an
empty list must not raise `ZeroDivisionError`."*

**Execution outcome:** re-run genuinely fails on `buggy/` with
`ZeroDivisionError: division by zero` at `stats.py:3` — exactly the
reported defect, and would pass under a fix that stops the crash
regardless of what value it returns instead.

**Gate/claim outcome — the format-compliance failure:** the repaired
candidate's own logic needed no exact-value grounding at all (the bare
call produces zero AST-extractable contracts). But the agent wrote its
EVIDENCE block under a `## EVIDENCE` markdown header inside
`trajectory.md`, not the required literal `EVIDENCE:` marker in its final
response — the orchestrator's parser correctly reports this as
unparsable (`parse_ok: false`, `"no EVIDENCE:/END_EVIDENCE block found"`
in the agent's *actual final message*, which is prose only). Per the
gate's design, an unparsable block is `UNSUPPORTED` regardless of whether
any contract needed grounding. **Final claim: `INSUFFICIENT_EVIDENCE`.**

**Oracle measurement (separate, later, never fed back into the claim
above):** `VALID` — all five conditions satisfied. The repair was
correct; the system just never said so.

## Agent self-reported (not independently re-verified beyond the execution result above)

`trajectory.md` for the repair round is unusually thorough — includes a
correct diagnosis of why the original `pytest.raises` framing was wrong,
the full traceback observed, and a "Files read / commands run" list. Its
existence and content don't change the claim outcome above: the format
rule applies to the *final response*, not `trajectory.md`, by design (see
`GENERATION_PROMPT_TEMPLATE`/`REPAIR_PROMPT_TEMPLATE` in
`src/bugproof/advanced.py`).

## Human checkpoint / orchestration decision

None — this outcome was discovered during the standard batch pipeline
run, then written up as a named finding in
`evidence/advanced/ablations/special_review.md` rather than acted on
(the mechanism was not patched further to special-case this).
