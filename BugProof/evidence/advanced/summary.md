# Phase 3 — Execute-Before-Claim + Evidence Gate + Bounded Repair

## Mechanism

Three ablation rungs on top of the frozen Phase 2 baseline (A):

- **B — execute before claiming.** Reuses A's 12 frozen candidates
  verbatim (zero new subagent calls — B's generation prompt would be
  byte-identical to A's). The orchestrator independently re-runs each
  candidate against a fresh copy of `buggy/` and computes the claim
  mechanically, never trusting the agent's original self-report.
- **C — Evidence/Contract Sufficiency Gate.** One fresh one-shot
  generation per case, under a prompt that mandates a required execution
  report plus a structured `EVIDENCE` block. A deterministic, non-LLM
  checker (`src/bugproof/advanced.py`) independently AST-detects every
  exact `==`/`!=`/`is`/`is not`/`pytest.raises(...)` contract the
  candidate's own code asserts and requires each one to be genuinely
  grounded — by a verified literal quote, or (numeric contracts only) a
  safely-recomputed arithmetic derivation from the test's own setup
  numbers plus a quoted rule. Labeling a value "qualitative" does not
  exempt it if the AST shows an exact comparison; that loophole was
  designed in, caught in review, and closed before Step 0 (see
  `config.json`'s `evidence_gate_mechanism_history` and `advanced.py`'s
  module docstring for the full account, including a second, self-caught
  fix for list/tuple literals mid-batch, before any case was scored).
- **D — bounded repair.** Reuses C's candidate; spends exactly one
  additional, fully self-contained repair subagent call *iff* C's claim
  wasn't already `VERIFIED_REPRODUCTION`. No second repair, ever.

No oracle feedback enters any runtime decision at any rung — auditable
directly from the trajectory bundles (`evidence/advanced/trajectories/
<case_id>/bundle.json`), and structurally enforced: `advanced.py` never
imports `bugproof.verdict`. The benchmark oracle (`evaluate()`) is run
separately, later, against every final frozen candidate for every
case/variant regardless of the system's own claim — for measurement only.

**Model fairness:** no override. `ADVANCED_CONFIG` inherits `model:
"sonnet"` and `subagent_type: "general-purpose"` directly from
`BASELINE_CONFIG` — every generation and repair call in this round used
the identical model/subagent configuration as the frozen Phase 2 baseline.

## Ablation results (all four numbers independently reproduced by
`python eval/run_advanced_replay.py`, which recomputes VRR fresh from
the frozen candidates and confirms it matches what orchestration recorded
live — see "Offline reproduction" below)

| Variant | N | Claim Rate | VRR | FCRR | Δ Claim vs A | Δ VRR vs A | Δ FCRR vs A |
|---|---|---|---|---|---|---|---|
| A (baseline) | 12 | 12/12 (100.0%) | 9/12 (75.0%) | 3/12 (25.0%) | — | — | — |
| B (+ execute-before-claim) | 12 | 12/12 (100.0%) | 9/12 (75.0%) | 3/12 (25.0%) | 0.0 | 0.0 | 0.0 |
| C (+ Evidence Gate) | 12 | 4/12 (33.3%) | 8/12 (66.7%) | 1/4 (25.0%) | −66.7 | −8.3 | 0.0 |
| D (+ bounded repair) | 12 | 8/12 (66.7%) | 9/12 (75.0%) | 3/8 (37.5%) | −33.3 | 0.0 | +12.5 |

Full per-stage latency/token breakdown in `ablations/{B,C,D}_metrics.json`
(`latency_seconds.incremental_*`/`cumulative_*`, with an explicit p95
caveat at n=12; `tokens.total`). Headline: B adds ~0.8s median (pure
`pytest` re-run, no LLM); C's fresh generation costs a full LLM call per
case (median ~53s, ~56k tokens); D adds a further ~78s median only on the
8 cases where repair fired.

## Per-case outcomes (A/B/C/D), oracle status/reason

| case_id | A | B | C (claim/oracle) | D (claim/oracle) |
|---|---|---|---|---|
| cart_coupon_ordering | VALID | VALID | VERIFIED/VALID | VERIFIED/VALID |
| contact_dedup_case_sensitivity | VALID | VALID | INSUFFICIENT/VALID | INSUFFICIENT/VALID |
| csv_quoted_field_parsing | WRONG_SYMPTOM | WRONG_SYMPTOM | INSUFFICIENT/WRONG_SYMPTOM | VERIFIED/WRONG_SYMPTOM |
| discount_unit_mismatch | VALID | VALID | VERIFIED/VALID | VERIFIED/VALID |
| empty_list_average_crash | FAILS_ON_FIXED | FAILS_ON_FIXED | EXECUTION_FAILURE/PASSES_ON_BUGGY | INSUFFICIENT/VALID |
| inventory_negative_quantity | VALID | VALID | VERIFIED/WRONG_SYMPTOM | VERIFIED/WRONG_SYMPTOM |
| off_by_one_pagination | VALID | VALID | INSUFFICIENT/VALID | INSUFFICIENT/VALID |
| reminder_lead_time_units | VALID | VALID | VERIFIED/VALID | VERIFIED/VALID |
| roster_lookup_wrong_exception | FAILS_ON_FIXED | FAILS_ON_FIXED | EXECUTION_FAILURE/PASSES_ON_BUGGY | **VERIFIED/VALID** |
| stale_cache_between_users | VALID | VALID | INSUFFICIENT/VALID | INSUFFICIENT/VALID |
| ttl_cache_boundary | VALID | VALID | INSUFFICIENT/VALID | VERIFIED/WRONG_SYMPTOM |
| username_normalization | VALID | VALID | INSUFFICIENT/VALID | **VERIFIED/VALID** |

`inventory_negative_quantity` (this round's smoke-test case, kept as its
real C result per the Step 0 gate) is the one case where fresh regeneration
itself — independent of any gate mechanism — produced a different,
also-legitimate but oracle-incompatible test (asserts the invariant
directly rather than `pytest.raises(ValueError)`, which is what this
case's reference expects) than Phase 2's baseline sample. This is
one-shot sampling variance, not a mechanism effect; see "Interpretation"
below.

## Special-review answers (required by the brief)

Full detail with quoted gate output in `ablations/special_review.md`.
Short version: for `empty_list_average_crash` and
`roster_lookup_wrong_exception`, C's mechanical **execution** gate — not
the evidence gate — is what caught both agents claiming
`VERIFIED_REPRODUCTION` while their own `pytest.raises(...)` tests
actually *passed* on `buggy/` (asserting the current buggy behavior
instead of the desired one). Both exception contracts were already
evidence-grounded; the defect was symptom-direction. D's repair fixed
`roster_lookup_wrong_exception` completely (now oracle-`VALID`);
`empty_list_average_crash`'s repair fixed the same defect correctly but
lost `INSUFFICIENT_EVIDENCE` to a format-compliance failure (EVIDENCE
block placed under a non-conforming header in `trajectory.md` rather than
in the final message), not to weak grounding. For
`csv_quoted_field_parsing`: execution/symptom verification correctly
certifies a genuine reproduction in both C and D, but the oracle's own
`message_pattern` is a literal lifted from `reference_test.py`'s example
text, structurally invisible to every B/C/D arm — predicted before any
live call, confirmed after. Not a gate failure; a benchmark-oracle
limitation already known from Phase 2, out of scope to fix here.

## Two mechanism limitations found live, beyond the required scope

(Full detail, with every occurrence named, in `ablations/special_review.md`.)

1. **EVIDENCE format fragility.** The line-prefix, `---`-delimited format
   is un-gameable by a dishonest agent but fragile to an honest one's
   ordinary stylistic variation (numbered lists without `---`, lowercase
   field names, evidence placed in `trajectory.md` under a markdown
   header instead of the final response). Observed independently at least
   4 times across 12 generations + 8 repairs. Real cost: several
   `INSUFFICIENT_EVIDENCE` outcomes trace to format non-compliance, not to
   genuinely ungroundable evidence.
2. **Computed expected values evade the AST extractor.** A comparison
   against a `Name` bound to a `Call` (e.g. `len(setup_list)`,
   `1 + page_size`) is invisible to `extract_expected_contracts` —
   observed independently 3 times, always with good intent (deriving a
   value from real setup data instead of hardcoding it) but never checked
   either way. A disclosed, deliberate scope boundary — closing it fully
   would require resolving arbitrary in-code arithmetic, which starts to
   look like the general symbolic-execution framework the brief
   explicitly ruled out.

## Trajectory capture — what is and isn't independently verified

Phase 2 lost 11/12 raw subagent transcripts to Claude Code's task-output
retention window. Phase 3 does not depend on that mechanism at all:
everything in `evidence/advanced/trajectories/<case_id>/bundle.json` —
exact prompt sent, the agent's full final message, the final workspace
file contents (read back directly via `Read`, not trusted from the
agent's own report), the orchestrator's own independent execution result,
the deterministic gate's full computed result, repair prompt+result where
applicable, final claim — was written to disk by the orchestrator
synchronously, in the same turn as each step, before this write-up began.
Proven working via the Step 0 smoke test (`inventory_negative_quantity`)
before the 12-case batch started, per the brief's own stop-gate.

**Disclosed gap, unchanged from the design plan:** the agent's internal
step-by-step tool-call sequence inside its own subagent turn is not
independently captured this way — only its final message and final
file-system state are. Each generation/repair prompt asks the agent to
self-report a "Files read / commands run:" list in `trajectory.md`;
that list is self-reported, not independently re-verified, and is
recorded as such.

## Offline reproduction

```bash
python -m pytest -q                     # full suite incl. tests/test_advanced_gate.py
python -u eval/harness_selftest.py      # Phase 0-2 unaffected
python eval/run_advanced_replay.py      # no LLM call -- recomputes VRR fresh
                                         # from evidence/advanced/candidates/,
                                         # confirms it matches trajectories/*.json
```
Regenerating the candidates themselves (C's generation, D's repair) is not
offline-reproducible in this environment, for the same reason Phase 2's
baseline generation wasn't — see `src/bugproof/baseline.py`'s module
docstring. What *is* fully offline-reproducible is re-scoring the frozen
candidates and re-deriving every number in this document from them.
