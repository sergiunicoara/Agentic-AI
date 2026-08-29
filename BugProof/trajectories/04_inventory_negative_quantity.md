# Episode 4 — `inventory_negative_quantity`: delivered claim, oracle WRONG_SYMPTOM

**Demonstrates:** a false-confidence outcome the execution and evidence
gates did **not** catch, because nothing about it was actually dishonest —
the candidate is well-evidenced and genuinely fails on `buggy/` for the
reported reason; it just tests a different, also-legitimate remediation
shape than the one this case's oracle happens to expect. This was also
this round's Step 0 smoke-test case, kept as its real result once the
smoke gate passed.

## Source artifacts (original, unmodified)

| Path | SHA-256 |
|---|---|
| `cases/inventory_negative_quantity/report.md` | `724d42ad1e9ff57e3ae7532d4cd54516287537afbcb7e2e85d31c562fa5118cc` |
| `evidence/advanced/trajectories/inventory_negative_quantity/bundle.json` | `85a223be2c23f1d9b1bdd416d3fe3adc453dca14c5d14c02189a3ae3c49b831a` |
| `evidence/advanced/candidates/C/inventory_negative_quantity/candidate_test.py` | `40638a66a1c2d539de1b26bc3688d5344010c6af117293a5fe6910876e52ee3b` |

(D's candidate is byte-identical to C's — `repair_fired: false`, since C's
claim was already `VERIFIED_REPRODUCTION`.)

## Input — bug report (directly captured, verbatim)

> One of our warehouse SKUs showed up as -3 units in stock in this week's
> export. Stock counts should never go negative — something let an
> adjustment through that removed more units than were actually on hand.
> Not sure if this is a data entry problem or something in the adjustment
> logic itself.

## Final candidate (C)

Sets up 2 units on hand, applies a -5 adjustment, asserts the raw
arithmetic result (`result == -3` — grounded by a literal quote, "-3 units
in stock", from `report.md`), then asserts the actual invariant:
`result >= 0` and `stock["SKU-1"] >= 0` — a threshold check, not an exact
equality, so it's outside the AST contract extractor's scope by design
(`>=` is not one of the tracked operators).

## Execution outcome (orchestrator-measured)

`OK` — 1 failing testcase on `buggy/`, `AssertionError: assert -3 >= 0`,
directly matching the report.

## Gate/claim outcome

Evidence Gate: `SUPPORTED` — the one exact contract (`equality: -3`) is
grounded by a real quote; the `>= 0` invariant checks are correctly
outside the gate's scope (not an exact `==`/`!=`/`is`/`is not` comparison).
**Final claim: `VERIFIED_REPRODUCTION`.**

## Oracle measurement (deterministic, separate, later)

**`REJECTED / WRONG_SYMPTOM`** — `expected exception_type='ValueError'
message_pattern='DID NOT RAISE'; observed failure text did not match`.
This case's reference solution expects the fix to *reject* an invalid
adjustment by raising `ValueError`, not silently clamp/allow it while an
invariant assertion catches the after-the-fact symptom. Both are
legitimate ways to fix the underlying bug; the candidate tests one, the
oracle's reference expects the other. Nothing in `report.md` — the only
input this candidate ever saw — states which remediation shape is
correct.

## Agent self-reported (not independently re-verified beyond the execution result above)

`trajectory.md` reports reading `report.md` and `buggy/inventory.py`,
running the test once via temp-copy into `buggy/`, observing the failure,
and confirming `buggy/` was left byte-for-byte unchanged (also confirmed
independently by the orchestrator's own diff, `buggy_tampering_detected:
false`).

## Human checkpoint / orchestration decision

This was the Step 0 smoke-test case: the full pipeline (execution → gate
→ claim → oracle measurement → bundle persistence → reopen-from-disk
validation) was run and manually inspected on this case *before* any of
the other 11 cases, per the Phase 3 plan's stop-gate. It passed every
required check and was kept as this case's real C result rather than
discarded and regenerated — see `CHANGELOG.md`'s Phase 3 entries and
`evidence/advanced/summary.md` for the full smoke-test record.
