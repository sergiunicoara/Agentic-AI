# BugProof

Turns a vague, human-written bug report into a verified failing regression
test. See `CHANGELOG.md` for the full experimental history and `evidence/`
for every phase's raw artifacts.


## Who this is for

BugProof is for developers and support engineers who receive a bug report and
need to turn it into a regression test before fixing the defect.

The bottleneck is not simply generating a failing test. A coding agent can
produce a red test that fails for the wrong reason, encodes the current buggy
behavior, or invents an expected contract that the report never specified.
Such a test looks like progress while potentially sending the developer toward
the wrong diagnosis.

BugProof makes that failure mode measurable. It generates a regression-test
candidate, executes it, checks whether the asserted behavior is supported by
the available evidence, and either delivers the reproduction or abstains.

The value is not “more generated tests.” It is reducing false-confident bug
reproductions while making the cost of abstention and manual fallback explicit.

## Headline result (12-case corpus)

Two frozen, non-dominated operating policies exist in this system today —
a coverage policy and a precision policy. Moving from coverage to
precision on this corpus:

- **false-confident delivered reproductions: 3 → 1**
- correct delivered reproductions: 9 → 4
- coverage: 100% → 41.7%
- claim precision: 75% → 80%

Neither number is free. The precision policy eliminates two false
deliveries but also delivers five fewer correct reproductions than the
coverage policy. Measured against its own ten oracle-valid internal
candidates, it withholds six — see **Abstention is not free** below. Full
absolute counts, oracle rejection breakdown, and source-artifact hashes:
[`evidence/final/final_metrics.json`](evidence/final/final_metrics.json).

*(An internal Candidate Validity Rate, CVR — oracle-VALID regardless of
whether a candidate was ever delivered to a user — moves 75% → 83.3% over
the same change. That number describes candidate quality, not delivery,
and is not the primary result; see Terminology below before quoting it.)*

## Two operating points, not one system

| Policy | Definition | Correct delivered | False delivered | Coverage | Claim Precision |
|---|---|---|---|---|---|
| **coverage** | frozen baseline (A): claim on every case, no abstention | 9 | 3 | 100% | 75.0% |
| **precision** | frozen D_exec: repair only `EXECUTION_FAILURE` C-outcomes, keep every other C result (including abstentions) unchanged | 4 | 1 | 41.7% | 80.0% |

*On the 12-case evaluation corpus — not a claim of universal Pareto
optimality.* Every other measured policy is dominated by one of these two
on this corpus (B is metric-identical to A; D is dominated by A; C is
dominated by D_exec). Full pairwise dominance derivation:
`evidence/final/final_metrics.json`'s `pareto` block.

Mode selection between the two is an explicit **operator choice**, never
automatic or oracle-derived at runtime — see `evidence/advanced/config.json`
and `src/bugproof/advanced.py`'s module docstring for the structural
guarantee (the gate/claim code never imports the oracle).

### When to prefer which

Symbolic cost model (not a measured empirical claim — see caveat below):
`Cost = M × (N − DV) + DF × P`, where `M` = manual reproduction cost, `P` =
additional wasted-investigation cost of trusting a false delivered
reproduction, `DV`/`DF` = delivered-valid / false-delivered counts.

For coverage (A: DV=9, DF=3) vs precision (D_exec: DV=4, DF=1) on this
corpus:

```
Cost(coverage)  = 3M + 3P
Cost(precision) = 8M + P
Break-even: 2P = 5M  ->  P/M = 2.5
```

**precision has lower modeled cost when `P > 2.5M`**; **coverage has lower
modeled cost when `P < 2.5M`**. No claim is made about the real value of
`P/M` — the only human-timing evidence available (an n=3 pilot) is
explicitly LOW confidence and is not used to derive or justify this ratio.

## Abstention is not free

D_exec's internal candidates are oracle-valid in 10 of 12 cases (CVR
83.3%) — but it only *delivers* 4 of those 10 as claims. On this corpus,
the precision policy withheld **six of ten** oracle-valid candidates while
eliminating two false deliveries relative to the coverage policy. A gate
that withholds a correct answer still sends the user back to manual work
— that cost doesn't disappear because it isn't a false positive.

## Terminology

- **CVR** (Candidate Validity Rate) — `oracle-VALID candidates / total
  cases`, regardless of delivery. This is what earlier frozen Phase 2/3
  artifacts called **VRR** — same formula, renamed here for clarity from a
  delivery perspective. Those artifacts (`evidence/baseline/summary.md`,
  `evidence/advanced/summary.md`, `ablations/{A,B,C,D,D_exec}_metrics.json`,
  `D_exec_summary.md`) are historical and were not rewritten.
- **DVRR** (Delivered Valid Reproduction Rate) — `delivered AND
  oracle-VALID / total cases`. Requires actual delivery; not the same
  question as CVR.
- **Claim Precision** — `delivered-valid / all delivered`.
- **Coverage** — `delivered / total cases` (was "Claim Rate").
- **False Delivered Claims** — absolute count of delivered claims the
  oracle rejects.

Full definitions with formulas: `evidence/final/final_metrics.json`'s
`metadata.metric_definitions`.

## Evidence map

- `evidence/baseline/` — Phase 2 frozen one-shot baseline (A).
- `evidence/advanced/` — Phase 3 execute-before-claim / Evidence Gate /
  bounded repair (B/C/D), the offline D_exec ablation, and the
  delivery-perspective audit.
- `evidence/final/final_metrics.json` — canonical, source-hashed metrics
  for A/B/C/D/D_exec, programmatically derived (see
  `eval/build_final_metrics.py`).
- `CHANGELOG.md` — the full evidence-driven decision history, including
  what was tried, measured, kept, and rejected.

## Reproduce the numbers

No LLM call required for any of these — pure oracle replay / arithmetic
over already-frozen candidates and results:

```bash
python -m pytest -q
python -u eval/harness_selftest.py
python eval/run_advanced_replay.py
python eval/run_dexec_replay.py
python eval/compute_delivery_audit.py
python eval/build_final_metrics.py
```

Regenerating the candidates themselves (Phase 2's baseline, Phase 3's C
generation and D repair) is not offline-reproducible in this environment
— see `src/bugproof/baseline.py`'s module docstring.


## Main failure mode

The main failure mode is **over-abstention**. The precision policy contains 10
oracle-valid candidates internally but safely delivers only 4 valid
reproductions. Six correct candidates are withheld while two false deliveries
are eliminated relative to the coverage policy.

This is why CVR is not the primary product metric: a correct internal candidate
that is not delivered still sends the user back to manual work.

## Hot take

> **Abstention is not free.**

A gate that withholds a correct answer still costs the user manual work. On this
12-case corpus, the precision policy withheld six of ten valid candidates while
eliminating two false deliveries. The practical lesson is to repair observable
failure rather than automatically repairing uncertainty, and to measure what
the user actually receives.
