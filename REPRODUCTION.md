# Reproduction guide

For a judge starting from a fresh checkout or unzipped submission of this
repository. No prior familiarity with the codebase assumed.

## Environment

- **OS:** developed and last verified on Windows 11 (PowerShell/Git Bash).
  Nothing in the codebase is Windows-specific (pure Python + subprocess
  calls to `sys.executable -m pytest`), so Linux/macOS should work
  identically, but only the Windows path has been exercised in this
  submission.
- **Python:** `>=3.10` (declared in `pyproject.toml`); developed and
  verified against **3.11.9**. Any 3.10+ interpreter should work.
- **Virtualenv:** recommended, not required. The only runtime dependency
  is `pytest>=8.4,<9`.
- **Install:**
  ```bash
  pip install -e .
  ```
  (installs `bugproof` from `src/` per `pyproject.toml`'s
  `[tool.setuptools.packages.find]`, plus `pytest`).

## API keys / network

**None required for anything in this guide.** Every command below is pure
oracle replay or arithmetic over already-frozen files — no LLM call, no
network access, no API key of any kind. This is verified mechanically, not
just claimed: see `evidence/final/integrity_check_result.json` and the
grep-based no-LLM-import check recorded in `CHANGELOG.md`'s final audit
entry.

## A. Offline reproducible (no API key, no network)

Run from the repository root, in order:

```bash
python -m pytest -q
```
Expected: `30 passed` (BugProof's own unit/regression suite, including
`tests/test_advanced_gate.py`'s Evidence Gate coverage). Runtime: ~60-95s
observed.

```bash
python -u eval/harness_selftest.py
```
Expected: a table of all 12 corpus cases, each `reference: VALID`; two
cases (`empty_list_average_crash`, `off_by_one_pagination`) flagged `twin`
with their decoy's rejection reason shown; final line
`OK: 12 cases, 2 twin decoys confirmed flipping the verdict.`, exit 0.
Runtime: ~25s-a few minutes observed (see Troubleshooting).

```bash
python eval/run_advanced_replay.py
```
Expected: three lines (`B:`, `C:`, `D:`) each showing `Claim`/`VRR`/`FCRR`
as `x/12` fractions, then `All replayed oracle verdicts match what was
recorded live during orchestration.` Runtime: under a minute typically.

```bash
python eval/run_dexec_replay.py
```
Expected: one line, `D_exec: Claim 5/12  VRR 10/12  FCRR 1/5`, plus the
two case IDs eligible for repair under D_exec's policy.

```bash
python eval/compute_delivery_audit.py
```
Expected: a 5-row table (A/B/C/D/D_exec) of CVR/DVRR/Precision/FalseDeliv/Coverage.

```bash
python eval/build_final_metrics.py
```
Expected: `Integer-first audit: ALL PASS`, then the same 5-row table, the
Pareto pairwise-dominance dict, and `Non-dominated operating points on
this corpus: ['A', 'D_exec']`. **This is the canonical source of every
final metric in this submission** — see "Canonical metrics" below.

None of the six commands above call any LLM, spawn any network request, or
require any environment variable. All read only already-frozen files
under `cases/`, `evidence/baseline/`, and `evidence/advanced/`, and write
only new derived files (`evidence/advanced/results/`,
`evidence/advanced/ablations/*_metrics.json`, `evidence/final/`).

## B. Not deterministically regenerated offline

Evaluation is fully reproducible offline from frozen candidates: oracle
verdicts, delivery metrics, and Pareto analysis can be recomputed without
API keys or network access. Candidate regeneration requires model access
and is non-deterministic, so generated candidates are frozen and
hash-tracked. Specifically **not** reproducible by a judge without model
access: the original candidate-generation subagent calls that produced
`evidence/baseline/candidates/*/candidate_test.py` (Phase 2) and
`evidence/advanced/candidates/{C,D}/*/candidate_test.py` (Phase 3) in the
first place. Those calls happened once, live, and their outputs are frozen
in the repository; re-running generation would use a different model
session and is not guaranteed to reproduce the same text. What *is*
reproducible is scoring those exact frozen outputs against the oracle —
which is everything in section A.

## Canonical final metrics

`evidence/final/final_metrics.json` — every number in this file is derived
programmatically by `eval/build_final_metrics.py` from frozen results
files, with an integer-first audit (every count checked by exact equality
against explicit expectations before any percentage is computed) and
SHA-256-hashed `source_artifacts` for traceability. `README.md`'s headline
numbers, `CHANGELOG.md`'s final entries, and every curated trajectory
summary in `trajectories/` are drawn from this file — if a judge finds a
number elsewhere that disagrees with `final_metrics.json`, treat
`final_metrics.json` as authoritative and the other location as a
documentation bug.

## Frozen candidate evidence

- `evidence/baseline/candidates/<case_id>/candidate_test.py` — Phase 2 (A).
- `evidence/advanced/candidates/{B,C,D,D_exec}/<case_id>/candidate_test.py`
  — Phase 3 and the offline D_exec ablation.
- `evidence/advanced/trajectories/<case_id>/bundle.json` — full per-case
  record (prompt sent, agent's final message, execution result, gate
  result, claim, oracle measurement) for every case across B/C/D.
- `trajectories/` (repository root) — 3-5 curated, human-readable
  summaries of the above, for a judge who doesn't want to read all 12 raw
  JSON bundles; each links back to its original source path and SHA-256.

## Historical VRR terminology note

Historical evaluation scripts may print VRR. In current submission-facing
terminology, that same candidate-level metric is called CVR (Candidate
Validity Rate).

- **CVR** = oracle-VALID frozen candidates / total cases. Does not imply
  the candidate was ever delivered to a user.
- **DVRR** = delivered reproduction claims whose delivered candidate is
  oracle-VALID / total cases. Requires actual delivery.

Frozen historical artifacts (`evidence/baseline/summary.md`,
`evidence/advanced/summary.md`, `ablations/{A,B,C,D,D_exec}_metrics.json`,
`D_exec_summary.md`, `config.json`, `src/bugproof/advanced.py` docstrings,
and the `eval/run_advanced_replay.py`/`run_dexec_replay.py`/
`compute_delivery_audit.py` console output) were **not** edited merely to
rename VRR to CVR — they remain historical as originally written. Current
submission-facing documents (`README.md`, `evidence/final/final_metrics.json`,
this file) use CVR/DVRR/Claim Precision/Coverage exclusively, except where
explicitly explaining this alias.

## Troubleshooting

Only issues actually observed in this environment during this submission's
own preparation:

- **`eval/harness_selftest.py` occasionally takes several minutes instead
  of ~25 seconds**, with no error, just a long pause before printing its
  table. Reproduced once during final verification; not a hang -- it
  completed with exit 0 after ~4 minutes on a machine under heavier
  background load than usual. This is consistent with a documented,
  intermittent multi-minute stall in `sandbox.py`'s subprocess cleanup
  path (see the code comment on `run_pytest`'s `finally` block), correlated
  with antivirus scanning of newly-written temp files on Windows -- not
  something this guide's commands can avoid; if it happens, wait rather
  than retry.
- **`PytestCollectionWarning: cannot collect test class 'TestCaseResult'`**
  when running `pytest -q` — harmless. `TestCaseResult` in
  `src/bugproof/sandbox.py` is a plain dataclass that happens to start
  with "Test"; pytest's own collector warns about it, nothing fails.
