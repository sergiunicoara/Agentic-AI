# Improvement Changelog

This changelog follows micro1's required structure:

**Stage | What we tried and why | Evidence | Decision / learning**

Every meaningful iteration is linked to submitted evidence. Historical raw evidence is preserved unchanged; current submission-facing terminology uses **CVR** for the candidate-level metric historically called **VRR**.

---

## Phase 0 — Deterministic evaluation harness

**What we tried and why**  
Built `sandbox.py` for isolated pytest execution and `verdict.py` for the deterministic five-condition oracle before adding agent logic. Started with three hand-crafted cases plus twin decoys to prove the evaluator could distinguish a true reproduction from a near miss.

**Evidence**  
- `eval/harness_selftest.py`
- initial corpus cases and decoys
- `tests/` covering sandbox/verdict behavior

**Decision / learning**  
Kept. The evaluator had to be trustworthy before any baseline or advanced agent result could be meaningful.

---

## Phase 0 — Reproducibility and lifecycle hardening

**What we tried and why**  
Independent validation found intermittent evaluator stalls. Three rounds of fixes addressed:
1. third-party pytest plugin autoloading,
2. blocking cleanup in the per-candidate hot path on Windows,
3. automatic cleanup that reintroduced the same risk.

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` was added, destructive cleanup was removed from the evaluation path, and cleanup was moved to an explicit command.

**Evidence**  
- `tests/test_sandbox_lifecycle.py`
- `tests/test_corpus_terminates.py`
- repeated fresh-process runs, all exit 0

**Decision / learning**  
Kept. Evaluator lifecycle behavior was frozen after repeated successful termination.

---

## Phase 1 — Corpus growth and adversarial evaluator audit

**What we tried and why**  
Expanded the benchmark from 3 to 12 cases across 11 failure families with a deliberate difficulty spread. Ran an adversarial audit for leakage, ambiguity, reference overfitting, fixed-revision contamination, duplication, triviality, and oracle quality.

The audit found and corrected two real benchmark defects:
- an incorrect oracle assumption in `reminder_lead_time_units`;
- an over-broad fixed-revision rewrite in `roster_lookup_wrong_exception`.

**Evidence**  
- `cases/`
- `eval/harness_selftest.py`
- 12/12 reference tests VALID
- decoys rejected for their declared reasons
- twin decoys flip as expected

**Decision / learning**  
Kept. Corpus frozen at 12 cases for the baseline/advanced comparison.

---

## Phase 1 — Evaluator efficiency improvement

**What we tried and why**  
A valid candidate originally required four pytest subprocesses. The fixed native-suite baseline is a corpus invariant, so it was moved to a once-per-case check, and the candidate plus fixed native suite were evaluated together where safe.

**Evidence**  
- `tests/test_verdict_regression_classification.py`
- subprocess total reduced from 53 to 41 across the 12-case corpus
- verdict semantics unchanged

**Decision / learning**  
Kept. This improved efficiency without changing the oracle definition.

---

## Phase 2 — Fair one-shot baseline (A)

**What we tried and why**  
Measured a simple baseline before building advanced mechanisms. A general-purpose Claude Sonnet agent received only `report.md` and `buggy/`, generated one pytest candidate, and had no repair loop or oracle feedback.

The candidate was frozen before deterministic oracle evaluation.

**Evidence**  
- `evidence/baseline/results.json`
- `evidence/baseline/summary.md`
- `evidence/baseline/trajectories/`

**Measured delivery result**  
- correct delivered: **9**
- false delivered: **3**
- coverage: **12/12 (100%)**
- claim precision: **75%**
- CVR: **9/12 (75%)**

**Decision / learning**  
Established the high-coverage reference point. The baseline could produce plausible failing tests while still confidently encoding the wrong behavior or wrong symptom.

---

## Phase 2 — Benchmark correction after alternate valid reproduction

**What we tried and why**  
Review showed that `cart_coupon_ordering` was being rejected because its oracle was overfit to a literal value from the reference example rather than the underlying behavior. The oracle was corrected and tested against multiple independently-numbered reproductions.

A separate review of `csv_quoted_field_parsing` showed its rejection was genuine, so that oracle was deliberately left unchanged.

**Evidence**  
- `cases/cart_coupon_ordering/oracle.yaml`
- `tests/test_oracle_generality.py`
- `evidence/baseline/summary.md`

**Decision / learning**  
Kept only the demonstrated oracle correction. This established an important rule: fix benchmark defects only with independent evidence, not because a candidate scored poorly.

---

## Phase 3 — Evidence Gate design correction before live measurement

**What we tried and why**  
The first gate design allowed an agent to label unsupported exact values as qualitative evidence and bypass grounding. Before live evaluation, this was corrected with deterministic AST extraction of exact contracts plus literal or safely-derived evidence requirements.

Additional fixes covered safe arithmetic derivation and list/tuple literal contracts.

**Evidence**  
- `tests/test_advanced_gate.py`
- 18 deterministic gate tests

**Decision / learning**  
Kept. The gate must inspect what the test actually asserts rather than trusting the agent's evidence label.

---

## Phase 3 — Ablation B: execute-before-claim

**What we tried and why**  
Reused A's frozen candidates and added independent pytest execution before accepting a reproduction claim. No new candidate-generation calls were made.

**Evidence**  
- `evidence/advanced/results/B/`
- `evidence/advanced/ablations/B_metrics.json`
- `python eval/run_advanced_replay.py`

**Measured delivery result**  
- correct delivered: **9**
- false delivered: **3**
- coverage: **12/12 (100%)**
- claim precision: **75%**

**Decision / learning**  
Not selected as a separate operating point. On this corpus, B is delivery-metric-equivalent to A.

The mechanism still revealed an important failure mode later in fresh advanced generations: an agent can claim reproduction even when its own test passes on `buggy/`.

---

## Phase 3 — Ablation C: deterministic Evidence Gate

**What we tried and why**  
Added mandatory execution plus deterministic AST/evidence grounding before a claim could be delivered.

**Evidence**  
- `evidence/advanced/results/C/`
- `evidence/advanced/candidates/C/`
- `evidence/advanced/ablations/C_metrics.json`
- `evidence/advanced/trajectories/`

**Measured delivery result**  
- correct delivered: **3**
- false delivered: **1**
- coverage: **4/12 (33.3%)**
- claim precision: **75%**
- CVR: **8/12 (66.7%)**

**Decision / learning**  
Not selected. The gate reduced false deliveries but abstained too aggressively.

This exposed the central product trade-off: candidate correctness and safe delivery are different problems.

---

## Phase 3 — Ablation D: broad bounded repair

**What we tried and why**  
Added one bounded repair whenever C did not return `VERIFIED_REPRODUCTION`, including both execution failures and insufficient-evidence outcomes.

**Evidence**  
- `evidence/advanced/results/D/`
- `evidence/advanced/candidates/D/`
- `evidence/advanced/ablations/D_metrics.json`
- `evidence/advanced/trajectories/`
- `evidence/advanced/summary.md`

**Measured delivery result**  
- correct delivered: **5**
- false delivered: **3**
- coverage: **8/12 (66.7%)**
- claim precision: **62.5%**
- CVR: **9/12 (75%)**

**Decision / learning**  
**Removed as an operating point.**

D is strictly dominated by A on the 12-case evaluation corpus: it delivers fewer correct reproductions (**5 vs 9**) while delivering the same number of false reproductions (**3**).

This is the required removed experiment. Its main lesson was that repairing uncertainty can create additional claims without enough information to justify them.

---

## D_exec — Selective repair for observable execution failure only

**What we tried and why**  
Built a fully offline post-hoc policy from already-frozen C/D artifacts:

- if `C.final_claim == EXECUTION_FAILURE`, reuse the existing D repair;
- otherwise keep C unchanged;
- do not repair `INSUFFICIENT_EVIDENCE`.

No new model call or candidate generation was used.

**Evidence**  
- `evidence/advanced/candidates/D_exec/`
- `evidence/advanced/ablations/D_exec_metrics.json`
- `evidence/advanced/ablations/D_exec_per_case.json`
- `evidence/advanced/ablations/D_exec_summary.md`
- `python eval/run_dexec_replay.py`

**Measured delivery result**  
- correct delivered: **4**
- false delivered: **1**
- coverage: **5/12 (41.7%)**
- claim precision: **80%**
- CVR: **10/12 (83.3%)**

**Decision / learning**  
Kept as the second observed non-dominated operating point, alongside A, **on this 12-case corpus**.

The policy was selected post-hoc after observing A/B/C/D behavior on the same corpus. It is therefore **not independent held-out validation** and is not presented as proof of generalization.

The single change that contributed most was **restricting repair to observable execution failures rather than repairing uncertainty**.

---

## Final delivery-perspective audit

**What we tried and why**  
The historical metric called VRR counted oracle-valid candidates regardless of whether the system delivered them. That could overstate user value.

Submission-facing terminology was corrected without rewriting frozen historical evidence:

- **CVR — Candidate Validity Rate:** oracle-VALID frozen candidates / all cases
- **DVRR — Delivered Valid Reproduction Rate:** delivered reproduction claims whose delivered candidate is oracle-VALID / all cases
- **Claim Precision:** valid delivered claims / all delivered claims
- **False Delivered Claims:** delivered claims rejected by the oracle
- **Coverage:** delivered reproduction claims / all cases

All final percentages are derived only after exact integer counts match frozen evidence.

**Evidence**  
- `eval/build_final_metrics.py`
- `evidence/final/final_metrics.json`
- `evidence/advanced/ablations/delivery_audit_metrics.json`
- `evidence/advanced/ablations/delivery_audit_summary.md`

**Decision / learning**  
The final comparison is a trade-off, not a universal win.

### Observed delivery-level comparison

| Variant | Correct delivered | False delivered | Coverage | Claim precision | Status |
|---|---:|---:|---:|---:|---|
| A | 9 | 3 | 12/12 (100%) | 75% | high-coverage operating point |
| B | 9 | 3 | 12/12 (100%) | 75% | metric-equivalent to A |
| C | 3 | 1 | 4/12 (33.3%) | 75% | dominated by D_exec |
| D | 5 | 3 | 8/12 (66.7%) | 62.5% | **removed; dominated by A** |
| D_exec | 4 | 1 | 5/12 (41.7%) | 80% | precision operating point; post-hoc |

On this 12-case corpus, A and D_exec are the two observed non-dominated operating points.

---

## Final operating-point decision

The project exposes the trade-off in the evidence rather than hiding it.

### Coverage policy — A

- 9 correct delivered
- 3 false delivered
- 100% coverage
- 75% claim precision

### Precision policy — D_exec

- 4 correct delivered
- 1 false delivered
- 41.7% coverage
- 80% claim precision

Using the symbolic cost model

```text
Cost = M × (N - DV) + DF × P
```

where:
- `M` = manual reproduction cost
- `P` = additional investigation cost caused by a false delivered reproduction
- `DV` = delivered-valid reproductions
- `DF` = false delivered reproductions

the two policies break even at:

```text
P / M = 2.5
```

No empirical real-world value for `P/M` is claimed.

---

## Main failure mode

The main failure mode is **over-abstention**.

D_exec contains **10 oracle-valid candidates** internally but delivers only **4 valid reproductions**. Six correct candidates are withheld while two false deliveries are eliminated relative to A.

This means internal candidate validity is not a sufficient measure of product usefulness.

---

## Hot take

> **Abstention is not free.**

A gate that withholds a correct answer still sends the developer back to manual work.

On this 12-case corpus, the precision policy withheld six of ten valid candidates while eliminating two false deliveries.

The practical lesson is not “verify everything more aggressively.” It is:

> **Repair observable failure; do not automatically repair uncertainty, and measure what the user actually receives.**

---

## Reproducibility note

Historical artifacts may still use the term **VRR**. In current submission-facing terminology:

```text
historical VRR == current CVR
```

Frozen historical evidence was not rewritten.

The deterministic evaluation layer, delivery metrics, Pareto analysis, and final metrics are reproducible offline from frozen candidates. Candidate generation itself is model-dependent and non-deterministic, so generated candidates and trajectories are frozen and hash-tracked rather than claimed to be deterministically regenerable.
