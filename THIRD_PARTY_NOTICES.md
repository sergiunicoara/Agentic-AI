# Third-party notices

Covers dependencies actually used and concepts actually credited by this
project. Nothing below is vendored code unless explicitly stated.

## Conceptual inspiration — fail-to-pass formalization

BugProof's core correctness criterion is a fail-to-pass evaluation pattern:
a regression test must collect, fail on the buggy implementation for the
reported symptom, pass on the fixed implementation, and avoid introducing a
fixed-suite regression. In this project, that criterion is implemented by the
five-condition oracle in `src/bugproof/verdict.py`.

The conceptual lineage is credited to:

- **SWT-Bench** — Niels Mündler, Mark Niklas Müller, Jingxuan He, and Martin
  Vechev, NeurIPS 2024. MIT.
  https://github.com/logic-star-ai/swt-bench
  https://arxiv.org/abs/2406.12952

- **SWE-bench** — Carlos E. Jimenez, John Yang, Alexander Wettig, Shunyu Yao,
  Kexin Pei, Ofir Press, and Karthik R. Narasimhan, ICLR 2024. MIT.
  https://github.com/princeton-nlp/SWE-bench

**Neither project is vendored.** No code, Docker configuration, evaluation
harness, or dataset from SWT-Bench or SWE-bench is present in this repository.
The 12 bug-report/`buggy`/`fixed` triples under `cases/` and the evaluator in
`src/bugproof/verdict.py` were implemented for BugProof. The external work is
credited for the fail-to-pass evaluation concept, not for copied
implementation.

## Python packages

From `pyproject.toml`'s declared dependencies (the only runtime
dependency BugProof itself requires):

| Package | Purpose in this project | License |
|---|---|---|
| [pytest](https://docs.pytest.org/) `>=8.4,<9` | Test collection/execution — both BugProof's own unit suite (`tests/`) and the sandboxed subprocess runner (`sandbox.py`) that executes every candidate test against `buggy/`/`fixed/`. Not modified; used as an unmodified dependency via `sys.executable -m pytest`. | MIT (per installed package metadata: `pip show pytest` in this environment reports `License: MIT`) |

pytest's own transitive dependencies (`colorama`, `iniconfig`, `packaging`,
`pluggy`, `pygments`, per this environment's `pip show pytest` output) are
standard parts of the pytest install and are not separately used by
BugProof's own code.

**Not BugProof dependencies:** this development environment's `pip show`
also lists `pytest-asyncio` and `pytest-cov` as packages that depend on
pytest — those are unrelated, pre-existing packages on this machine, not
declared or required by `pyproject.toml`, and not used by any BugProof
code. (Their presence is exactly why `sandbox.py` sets
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` before every sandboxed run — so
whatever else happens to be installed on the host running the benchmark
never affects its determinism. See the code comment on `run_pytest()` in
`src/bugproof/sandbox.py`.)

## Model / API usage

Candidate generation (Phase 2 baseline, Phase 3 generation and repair)
used Claude Code `general-purpose` subagents, model pinned to Sonnet — see
`src/bugproof/baseline.py`'s module docstring for the full explanation of
why (no raw Anthropic API key was available in this environment) and what
was explicitly approved as the substitute. This is Anthropic's own Claude
Code product being used as intended, not a third-party dependency in the
sense of this notices file, but is disclosed here for completeness.

## No other third-party code

No other library, framework, dataset, or code sample from any other
project, paper, or repository was copied, adapted, or vendored into this
submission. If a reviewer identifies a resemblance not disclosed above,
it was not knowingly reused — this file reflects a deliberate, itemized
check of `pyproject.toml`, code comments, and `BUGPROOF_AGENT_BRIEF.md`
performed for this submission, not an exhaustive guarantee.
