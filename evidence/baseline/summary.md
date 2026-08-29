# Phase 2 — Fair One-Shot Baseline (corrected)

N = 12 cases. Same fixed prompt, same model, one attempt each, no oracle
feedback before freeze, no retry after evaluation. Full configuration:
`config.json`. Prompt source: `src/bugproof/baseline.py`. **No candidate
was regenerated for this correction pass** — all 12 frozen candidates from
the original run are unchanged; only the `cart_coupon_ordering` oracle
was corrected and the same 12 candidates re-evaluated.

## Benchmark correction applied first (see full detail below)

`cart_coupon_ordering`'s oracle was overfit to the reference test's
literal `$50+$50` arithmetic (`message_pattern: "95"`). A frozen Phase 2
candidate reproduced the identical defect with `$100+$100` and was wrongly
rejected. Corrected to match the failure's structural signature (a wrong
`checkout()` return value) instead of one example's numbers. **This is a
benchmark correction discovered by Phase 2's alternate valid reproduction,
not an agent improvement** — see `cases/cart_coupon_ordering/oracle.yaml`
and `tests/test_oracle_generality.py`.

## Aggregate metrics (corrected)

- **Claim Rate = 12/12 = 100.0%** (unchanged — claims are recorded facts from the original run)
- **VRR = 9/12 = 75.0%** (was 8/12 = 66.7% before the oracle correction)
- **FCRR = 3/12 = 25.0%** (was 4/12 = 33.3%)
- VALID: 9, rejected: 3
- Rejection distribution: `WRONG_SYMPTOM` = 1/12 (was 2/12), `FAILS_ON_FIXED` = 2/12 (unchanged), `PASSES_ON_BUGGY` = 0/12, `COLLECTION_ERROR` = 0/12, `SUITE_REGRESSION` = 0/12
- Harness ERROR/TIMEOUT: 0/12
- Latency/token figures are unchanged from the original run (same candidates, same subagent executions) — median latency 42.5s, total tokens 616,238. See `config.json`: `token_usage_available` is now correctly recorded as `true` (a prior draft of that file incorrectly said `false`; the Agent tool does expose a per-subagent token total, just not a dollar cost).

## Corrected result table

| case_id | difficulty | failure_family | claimed | oracle_verdict | rejection_reason | latency_s | tokens |
|---|---|---|---|---|---|---|---|
| cart_coupon_ordering | medium | ordering_state_dependent | REPRODUCED | **VALID** (was REJECTED/WRONG_SYMPTOM) | — | 52.3 | 50,567 |
| contact_dedup_case_sensitivity | medium | silent_incorrect_result | REPRODUCED | VALID | — | 42.0 | 49,680 |
| csv_quoted_field_parsing | hard | malformed_input_parsing | REPRODUCED | REJECTED | WRONG_SYMPTOM | 214.5 | 66,618 |
| discount_unit_mismatch | medium | incorrect_returned_value | REPRODUCED | VALID | — | 39.4 | 49,268 |
| empty_list_average_crash | easy | empty_input_crash | REPRODUCED | REJECTED | FAILS_ON_FIXED | 40.6 | 49,191 |
| inventory_negative_quantity | easy | input_validation | REPRODUCED | VALID | — | 51.3 | 49,674 |
| off_by_one_pagination | easy | boundary_off_by_one | REPRODUCED | VALID | — | 38.3 | 49,654 |
| reminder_lead_time_units | hard | multi_module_interaction | REPRODUCED | VALID | — | 34.3 | 49,554 |
| roster_lookup_wrong_exception | easy | wrong_exception_type | REPRODUCED | REJECTED | FAILS_ON_FIXED | 54.6 | 50,998 |
| stale_cache_between_users | medium | state_leak_between_calls | REPRODUCED | VALID | — | 40.9 | 49,484 |
| ttl_cache_boundary | hard | boundary_off_by_one | REPRODUCED | VALID | — | 63.2 | 52,054 |
| username_normalization | medium | transformation_normalization_error | REPRODUCED | VALID | — | 42.9 | 49,496 |

## Cart oracle correction — detail

**Original:** `message_pattern: "95"` — a literal substring tied to the
reference test's `$50+$50 @ 10%` example (buggy checkout = 95.0, expected
90).

**Evidence it was overfit, not a real distinguishing symptom:** the frozen
baseline candidate reproduces the *same* defect (coupon not applying to
items added after it) using `$100+$100 @ 10%` (buggy checkout = 190.0,
expected 180). Its failure text never contains "95". Independently running
that same candidate against `fixed/` returns PASS — confirming it is a
genuinely valid reproduction, rejected only because of the oracle's
literal-value dependency.

**Correction:** `message_pattern: checkout\(\)`. This is general because
it targets the *mechanism* of the defect — any test that fails specifically
because `ShoppingCart.checkout()`'s return value doesn't match expectation
will show `where <N> = checkout()` in pytest's assertion-rewrite output,
regardless of what numbers, coupon percentage, or item counts the test
uses. Verified empirically (not assumed) against both the reference's and
the frozen candidate's actual failure text before applying the change.

**Proof the fix is general, not re-overfit to the one known candidate:**
`tests/test_oracle_generality.py` proves **three** independently different
numeric reproductions all verify VALID under the corrected oracle:
1. the reference test itself ($50+$50 @ 10% → 95 vs 90)
2. the frozen Phase 2 baseline candidate ($100+$100 @ 10% → 190 vs 180) — verified directly via `evaluate()`, not just asserted
3. a new synthetic test written specifically for this regression check, using yet a third set of numbers never seen by either prior test ($60+$60 @ 20% → 108 vs 96)

No file was written with knowledge of what a *future* candidate might use — (2) and (3) use unrelated numbers from each other and from (1).

**Full deterministic oracle re-run confirming nothing else moved:**
`python eval/harness_selftest.py` → 12/12 references still VALID, all
decoys and twin decoys unchanged, exit 0.

## Corrected failure taxonomy — deterministic verdict + secondary engineering diagnosis

**`csv_quoted_field_parsing` — WRONG_SYMPTOM. CORRECTED DIAGNOSIS (previously
mischaracterized as an oracle false positive — that was wrong).**
Independent review ran this frozen candidate directly against `fixed/`:
**2 FAILED, 1 PASSED.** Verified again here, same result. The candidate's
own interpretation of CSV escaping — that a `"` only starts real CSV
quoting when it appears at the very start of a field (right after a
delimiter), and that a mid-field `"` is just a literal character to
preserve as-is — differs from the benchmark's actual intended contract,
where `fixed/linefmt.py` treats *any* `"` as a quote-state toggle
(matching the CSV `""`-escaping convention), regardless of field position.
The candidate correctly recognized "something is wrong with how the buggy
code handles a mid-field quote" but built an incorrect mental model of
what the *correct* behavior should be, and encoded that wrong model into
its assertions. **This is a genuine baseline miss, not an oracle
artifact.** The deterministic verdict correctly stops at WRONG_SYMPTOM
(the candidate's failure text never matches the reference's `"hi to the
customer"` pattern, because it uses different example strings); the
engineering diagnosis adds that even setting the oracle's literal-pattern
issue aside entirely, this candidate would still be rejected on
independent grounds (FAILS_ON_FIXED-equivalent) once run against
`fixed/`. **The CSV oracle was not modified** — doing so to pass this
candidate would reward an incorrect implementation.

**`empty_list_average_crash` — FAILS_ON_FIXED (unchanged).** Candidate
correctly reproduces the crash but asserts `average_score([]) == 0`; the
benchmark's fix returns `None`. `report.md` never specifies which
sentinel. **Diagnosis: assertion tests a wrong-but-plausible behavior,
caused by a genuine unstated contract in the bug report.**

**`roster_lookup_wrong_exception` — FAILS_ON_FIXED (unchanged).**
Candidate correctly reproduces the `IndexError` but expects `find_member()`
to return `None`; the benchmark's fix raises `KeyError`. Same
unstated-contract cause.

No `COLLECTION_ERROR`, `PASSES_ON_BUGGY`, or `SUITE_REGRESSION` occurred.

## Transcript recovery status

**11 of 12 raw subagent transcripts are unrecoverable.** Only
`discount_unit_mismatch_transcript.jsonl` (60,378 bytes) survives; the
other 11 came back as 0-byte copies, and — checked directly — the
*original* source files in the Claude Code task-output directory are also
0 bytes now, not just the copies. `mcp__ccd_session_mgmt__list_sessions`
does not list Agent-tool subagents as independently queryable sessions,
so there is no other retrieval path available in this environment. This
looks like a retention/eviction window on task output files, not
something broken by the copy step, but that mechanism isn't something
this session can introspect further.

**Not fabricated or reconstructed.** The 11 missing files were replaced
with explicit `*_transcript.MISSING.md` markers stating exactly this. Each
case's `trajectory.md` (agent-authored, not written by the orchestrating
session) and frozen `candidate_test.py` are unaffected and unchanged.

**The baseline was not rerun.** This was put to the human explicitly
rather than decided unilaterally: rerunning would create a new sample
(new candidates, new timing, new token counts), invalidating the current
frozen results. **Decision: do not rerun.** This is recorded as an
evidence limitation of the original baseline run, not silently
worked around — only 1 of 12 cases (`discount_unit_mismatch`) has a
recoverable raw transcript; the structured `trajectory.md` and frozen
`candidate_test.py` remain the available record for the other 11.

## Preliminary comparison to the n=3 Human + AI pilot

**Not merged into the n=12 dataset; reported separately.**

| | n=3 pilot | n=12 baseline (corrected) |
|---|---|---|
| Claim Rate | 3/3 = 100% | 12/12 = 100.0% |
| VRR | 2/3 = 66.7% | 9/12 = 75.0% |
| FCRR | 1/3 = 33.3% | 3/12 = 25.0% |
| median latency | 180s | 42.5s |

**Timing caveat (explicit, per review):** the pilot's ~180s median latency
must not be used as a headline developer-time claim. Those timings were
collected under time pressure, the pace was not sustainable, and the
artifacts/data behind them were not fully production-validated before
timing stopped. **Timing confidence for the pilot is LOW.** The
*correctness* observations (claim rate, VRR, FCRR as raw counts) may still
be reported, separately and clearly labeled n=3 preliminary, but the
latency figure specifically should not be presented as representative.

The VRR/FCRR percentages no longer land as close together as before the
correction (66.7%/66.7% → 75.0%/66.7%) — a reminder that the earlier
apparent agreement really was coincidental, not signal, exactly as flagged
last round.

## Ranked failure analysis (reassessed on the corrected benchmark)

**1. Dominant failure mode by count (corrected):** `FAILS_ON_FIXED` now
leads outright, 2/12 vs. `WRONG_SYMPTOM`'s 1/12 (previously tied at 2
each before the cart correction, and before the CSV recharacterization).

**2. Dominant failure mode by user harm:** `FAILS_ON_FIXED` remains the
more harmful pattern for a real user — both remaining `FAILS_ON_FIXED`
cases (`empty_list_average_crash`, `roster_lookup_wrong_exception`) encode
a *wrong contract* a developer could commit without noticing, unlike
`WRONG_SYMPTOM`, which fails loudly and visibly by never matching in the
first place.

**3. Which failures could objective execution detect cheaply?** All 3
remaining rejections. Every one of them produces a red test on `buggy/` —
a pure "run pytest, accept any red" baseline would have shipped all 3 as
done. The gate that catches them needs information the agent structurally
doesn't have: `fixed/`'s actual behavior (`FAILS_ON_FIXED` ×2) or a
correctly-scoped symptom description (`WRONG_SYMPTOM` ×1, now genuinely a
baseline miss, not an oracle artifact).

**4. Which failures require semantic symptom verification specifically?**
`csv_quoted_field_parsing`'s `WRONG_SYMPTOM` — and this one is now
confirmed to reflect a real model misunderstanding (of CSV escaping
semantics), not oracle scope. A semantic check here would need to compare
the candidate's *behavioral claim* (quotes only matter at field-start)
against the actual contract, which is exactly the kind of check that
needs `fixed/`-derived ground truth, not just better regex.

**5. Which failures would require repair/retry?** All 3. `FAILS_ON_FIXED`
×2 need to be told their guessed contract is wrong (not what the right one
is) before a retry could plausibly land differently.
`csv_quoted_field_parsing` needs the model to reconsider its assumption
about where CSV quoting rules apply — a bigger conceptual correction than
the other two, since it's a different failure family (parsing semantics)
from a return-value/exception-type guess.

**6. Which failures would NOT be solved by BugProof's proposed mechanism
(Evidence Gate = execution + symptom match before claiming, using only
`report.md` + `buggy/`)?** All 3, if "not solved" means "solved on the
first attempt with no additional information." An Evidence Gate built
strictly from what the agent can see cannot distinguish "my guessed
contract is plausible" from "my guessed contract is what the benchmark
actually implements" — that distinction is inherently oracle-only
information (see the runtime-vs-oracle framing below). What an Evidence
Gate *can* do is refuse to let the agent claim success at all when one of
these mismatches is present, converting a false "done" into an honest "I
could not verify this" — which has real value even without fixing the
guess.

**7. Is `COLLECTION_ERROR` actually dominant, or was the human pilot
anecdotal?** Unchanged from the prior round: anecdotal at n=3 (the
pilot's one failure), not reproduced at n=12 (zero occurrences, both
before and after this correction pass). Neither dataset is large enough
to settle this either way.

**8. Does the data justify:**
   - **execution-before-claim?** Still no new evidence — `PASSES_ON_BUGGY`
     = 0/12, unchanged.
   - **symptom gate?** Weaker case than before the correction: of the
     original 2 `WRONG_SYMPTOM` firings, 1 turned out to be an oracle
     defect (fixed) and only 1 is a genuine model miss. A symptom gate
     built the same way the original oracle was (compare against one
     hard-coded example) would risk reproducing exactly the false-rejection
     failure mode just corrected — this data argues for auditing any
     symptom-matching design for the same over-fitting risk, not for
     skipping the idea.
   - **repair loop?** Still the strongest case — now specifically 2/3
     rejections (`FAILS_ON_FIXED`) are unstated-contract guesses a
     narrowly-scoped repair signal could plausibly correct, and the third
     (`csv_quoted_field_parsing`) is a bigger conceptual miss a repair loop
     alone probably wouldn't fix without also supplying the missing
     semantic information.
   - **targeted retrieval?** No evidence, unchanged — nothing traces to
     insufficient repository search.
   - **second reviewer?** No evidence — same reasoning as before: nothing
     here is invisible-without-more-thought that a second pass over the
     *same* available information would catch, since the missing
     information in every remaining case is oracle-only, not something a
     second reviewer reading `report.md` + `buggy/` again would surface.

## Up to three candidate Phase 3 mechanisms (not implemented — human selects)

Each mechanism is stated with an explicit **runtime information** /
**oracle-only information** boundary. A mechanism is rejected if its
real-world version would need oracle-only information — the production
BugProof runtime never has `fixed/`; only this benchmark's evaluator does.

**1. Narrow repair loop for FAILS_ON_FIXED-shaped misses.**
- Observed failure → mechanism → expected metric moved: `FAILS_ON_FIXED`
  (2/12, unstated-contract guesses) → on rejection, tell the model only
  that its asserted expected value/exception for one specific assertion
  didn't hold, and allow one bounded retry → expected to raise VRR, lower
  FCRR.
- **Information available at runtime:** whether the candidate's own test
  passed or failed when actually run (execution result) — this is
  something a real user/CI system always has, with no oracle needed.
- **Information available only to the benchmark oracle:** *which specific
  assertion* was wrong and *why* — in production, the only feedback
  available is "the test still fails" or "the test now passes against
  whatever the real fix turns out to be," not a labeled diff against a
  known-correct answer. **This version of the mechanism, as scoped for
  the benchmark, uses oracle-only information and would need to be
  redesigned for real-world use** — e.g., replaced with something like
  "ask the model to consider whether its guessed contract for the
  unspecified return value is the only reasonable one, and enumerate
  alternatives" (a self-critique using only runtime-available information:
  the report text and its own prior attempt), which is a materially
  weaker but honestly-scoped version of this idea.
- Impact: high (targets the now-dominant failure mode). Simplicity:
  medium. Reproducibility: high (bounded, same deterministic gate).
  Latency/cost: one retry, only on rejection. Demo clarity: high, once
  reframed as self-critique rather than oracle-fed correction.

**2. Fix oracle symptom patterns to check the general defect class, not one
reference's literal example — evaluator work, not a Phase 3 agent
mechanism.**
- Observed failure → mechanism → expected metric moved: `WRONG_SYMPTOM`
  (1/12 remaining, `csv_quoted_field_parsing` — though this one is now
  known to also fail on `fixed/`, so fixing the oracle pattern alone would
  not flip it to VALID) → audit and, where warranted, correct oracle
  patterns for over-fitting → primarily protects VRR/FCRR from *future*
  oracle-scope false rejections as the corpus grows, rather than moving
  this run's numbers further.
- **Information available at runtime:** none needed — this is corpus
  authoring work.
- **Information available only to the benchmark oracle:** all of it, by
  design — this is oracle work, explicitly not an agent-facing mechanism.
  Listed because the cart correction shows it has real, demonstrated
  value, not because it belongs in a Phase 3 agent architecture.
- Impact: high per unit effort, scoped narrowly. Simplicity: high.
  Reproducibility: high. Latency/cost: none. Demo clarity: clear as a
  benchmark-quality story, not as an agent capability.

**3. Execution-before-claim (minimal Evidence Gate).**
- Observed failure → mechanism → expected metric moved: `PASSES_ON_BUGGY`
  (0/12 observed) → require the agent to execute its own candidate against
  `buggy/` and refuse to claim success if it doesn't fail → **no expected
  metric movement on this data**, since every candidate already did this
  (the fixed baseline prompt required it) and none needed catching.
- **Information available at runtime:** the candidate's own pass/fail
  result against the code the user actually has — fully runtime-available,
  no oracle needed. This is the only one of the three mechanisms with a
  production-honest, oracle-free real-world form as originally stated.
- **Information available only to the benchmark oracle:** none for this
  specific mechanism.
- Impact: none observed this run. Simplicity: high. Reproducibility: high.
  Latency/cost: low. Demo clarity: low here (nothing to demo since nothing
  fired), though it remains the cleanest mechanism from a
  runtime-information standpoint if the corpus grows to include cases
  where it would fire.

**Recommendation implied by the data, not a decision:** #1, reframed as
self-critique rather than oracle-fed repair, has the clearest
evidence-backed case for Phase 3 *and* the only honestly runtime-scoped
version of "use the rejection to try again." #2 is real, demonstrated
value from this very correction pass, but it's evaluator/corpus work, not
a Phase 3 agent mechanism — worth continuing regardless of what's chosen
for Phase 3. #3 has zero supporting evidence from this run and, if
adopted, would need to wait for a case where it actually fires to be
demonstrable.
