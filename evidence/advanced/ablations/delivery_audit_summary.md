# User-delivery audit of A/B/C/D/D_exec

**New final-analysis artifact only.** No candidate, claim, gate, or oracle
was touched; no LLM call was made. Computed entirely from already-frozen
files: `evidence/baseline/result_table.json` (A), `evidence/advanced/
results/{B,C,D}/results.json`, `evidence/advanced/ablations/
D_exec_per_case.json`. Script: `eval/compute_delivery_audit.py`. Raw
numbers: `delivery_audit_metrics.json`.

## Why this audit exists

Every prior Phase 3 report used "VRR" to mean *oracle-VALID regardless of
the runtime system's own claim* — a measure of how many candidates were
objectively good, not of how many the system actually told a user were
good. From a user-delivery perspective those are different questions: a
case where the oracle says VALID but the system said `INSUFFICIENT_EVIDENCE`
delivered nothing to a user, and shouldn't count toward "the system
verified this for you." This audit keeps that original metric — renamed,
not recomputed, not reinterpreted — and adds four metrics that condition
on whether a claim was actually delivered.

## Definitions

- **CVR (Candidate Validity Rate)** — `count(oracle_status == VALID) /
  total_cases`. Identical formula to what prior artifacts called VRR.
  Ignores delivery entirely; kept for continuity with the frozen ablation
  files, which are not being edited.
- **DVRR (Delivered Valid Reproduction Rate)** — `count(final_claim ==
  VERIFIED_REPRODUCTION AND oracle_status == VALID) / total_cases`. What a
  user actually received and that was actually correct.
- **Claim Precision** — `delivered-valid claims / all delivered claims`.
  Given the system claimed something, how often was it right. (Equal to
  `1 − FCRR_rate` by construction; computed independently here from raw
  counts, not derived algebraically, and both match.)
- **False Delivered Claims** — `count(final_claim == VERIFIED_REPRODUCTION
  AND oracle_status != VALID)`, absolute count. Identical to prior FCRR's
  numerator, presented on its own since it's the number that actually
  costs a user's time.
- **Coverage** — `delivered claims / total cases`. Identical formula to
  what prior artifacts called Claim Rate.

## Results (N=12 every variant)

| Variant | CVR | DVRR | Claim Precision | False Delivered Claims | Coverage |
|---|---|---|---|---|---|
| A | 9/12 (75.0%) | 9/12 (75.0%) | 9/12 (75.0%) | 3 | 12/12 (100.0%) |
| B | 9/12 (75.0%) | 9/12 (75.0%) | 9/12 (75.0%) | 3 | 12/12 (100.0%) |
| C | 8/12 (66.7%) | 3/12 (25.0%) | 3/4 (75.0%) | 1 | 4/12 (33.3%) |
| D | 9/12 (75.0%) | 5/12 (41.7%) | 5/8 (62.5%) | 3 | 8/12 (66.7%) |
| D_exec | 10/12 (83.3%) | 4/12 (33.3%) | 4/5 (80.0%) | 1 | 5/12 (41.7%) |

A/B's Claim Precision denominator is their full delivered-claims count
(12, since Coverage is 100%) — precision is `9/12 = 75.0%`, identical to
their FCRR-complement (`100% − 25.0%`).

Internal consistency check (performed, not assumed): for every variant,
`Claim Precision% + FalseDeliveredClaims_rate% == 100%` where
FalseDeliveredClaims_rate = FalseDeliveredClaims / Coverage_count — holds
exactly for all five rows.

## Reading the table

- **A and B are identical** on every metric — B added no measurable
  delivery-quality change on this corpus (consistent with every prior
  Phase 3 report: no baseline candidate ever failed conditions 1–2, so
  execute-before-claim had nothing to catch).
- **C and D_exec tie for fewest False Delivered Claims in absolute terms
  (1 each)**, but C does it mainly by not claiming much at all (Coverage
  33.3%, DVRR 25.0%), while D_exec claims more and still keeps the same
  false-claim count, giving it the best Claim Precision of any variant
  (80.0%) and the highest CVR
  (83.3%, exceeding even A/B) — but its Coverage (41.7%) and DVRR (33.3%)
  are both well below A/B's.
- **No variant simultaneously beats A/B on DVRR.** A/B still deliver the
  most *correct* claims in absolute terms (9 of 12), because they never
  withhold a claim — every other variant trades some correct deliveries
  away for fewer false ones.

## Sensitivity analysis — developer-time utility (symbolic only)

No empirical time-savings claim is made here. The n=3 human+AI pilot
remains separate, preliminary evidence with explicitly LOW timing
confidence (per its own caveat, repeated in every prior report) and is
not used in this derivation.

**Model.** Two symbolic costs, per case:

- `M` = cost of manual reproduction (what a developer pays when the system
  delivers no claim, or when a delivered claim later turns out to be
  false — a false claim doesn't remove the need to eventually reproduce
  the bug by hand, it delays it).
- `P` = the *additional* wasted-investigation cost of trusting a false
  delivered claim before discovering it's wrong (time spent building on,
  or debugging against, a test that doesn't actually hold on `fixed/`).

Declared simplifying assumptions (stated explicitly, not hidden): a
delivered **valid** claim costs the developer ≈0 (fully replaces manual
reproduction); a **not-delivered** case costs exactly `M`; a **delivered
false** claim costs `M + P` (the wasted investigation, *plus* still
needing to manually reproduce afterward, since the false claim didn't
actually solve anything).

**Per-variant expected total cost**, in terms of `DV` (delivered-valid
count) and `DF` (false-delivered count), over `N` cases:

```
Total_cost = M x (N - DV) + DF x P
```

(`N - DV` is every case that isn't a correct delivery — whether silent or
falsely claimed — each costing at least `M`; `DF` of those additionally
cost `P`.)

**Break-even P/M for A vs D_exec.** Using the counts above: `A: DV=9,
DF=3`. `D_exec: DV=4, DF=1`.

```
Total_cost(A)      = M(12-9) + 3P = 3M + 3P
Total_cost(D_exec) = M(12-4) + 1P = 8M + P

Break-even: 3M + 3P = 8M + P
            2P = 5M
            P/M = 5/2 = 2.5
```

Verified numerically (substituting `M=1, P=2.5` back into both cost
formulas): both equal `10.5`, confirming the algebra.

**Reading:** D_exec's expected total developer-time cost is lower than
A's *only when* `P > 2.5M` — i.e., only when the wasted-investigation cost
of a false delivered reproduction exceeds two and a half times the cost of
a plain manual reproduction. Below that ratio, A's near-total Coverage
(it almost never leaves a developer with nothing) outweighs its higher
false-claim count on pure expected-cost grounds, under this model.
This is a structural, symbolic result — it says nothing about the actual
value of `P/M` in practice, which was never measured and is not claimed
here.

## What this audit does not do

Per instruction: the policy behind C/D/D_exec was not reinterpreted,
re-tuned, or re-run based on these numbers. Nothing in `evidence/advanced/
candidates/`, `results/`, `trajectories/`, or the existing `{A,B,C,D,
D_exec}_metrics.json` / `*_summary.md` files was modified.
