# BugProof — Coding Agent Brief

> **Provenance note:** This brief was written before implementation, against the
> published evaluation criteria. It is included because it is the instruction
> that shaped the coding agent throughout, not a document written afterwards.

You are the coding agent building this project. Read this file completely before writing
any code. Re-read the "Working agreement" section at the start of every session.

---

## 0. Mission

Build **BugProof**: a system that turns a vague, human-written bug report into a
**verified** failing regression test.

The one-sentence claim the whole project defends:

> A failing test is not evidence of reproduction. The failure has to be the right failure.

A general coding agent, asked to "write a test that reproduces this bug," will happily
produce a test that goes red for the wrong reason — an import error, a broken fixture, a
different endpoint, a typo in the assertion — and report success. That test is worse than
no test: it looks like progress and it certifies nothing.

BugProof refuses to claim reproduction until execution proves it.

This is a submission for the micro1 Frontier Engineering Challenge (Aug 28–31, 2026).
Deliverable is a single `.zip`. Judging is out of 100 points against a published rubric.

---

## 1. Working agreement — read this every session

These rules override your defaults. These rules override your defaults. Violating them undermines the evidence the project rests on.

**R1 — No mechanism before evidence.**
Do not implement the Evidence Gate, the repair loop, the hypothesis planner, or any other
"advanced" component until the baseline has been run and its failures counted. The
Improvement Changelog must be a true record of what happened, in order. If you build
ahead, the changelog becomes fiction and the project loses the criterion it was designed
to win. When in doubt, build less and measure sooner.

**R2 — Stop at every gate.**
Phases below end with `=== STOP ===`. At a stop you produce the stated artifact, write a
short report of what you found, and **end your turn**. Do not begin the next phase. The
human reviews and releases you.

**R3 — Every claim is backed by a file.**
No number appears in the README, the changelog, or a commit message unless it was produced
by a run of `make eval` and written to `evidence/`. If you want to say something improved,
point at the JSON.

**R4 — Dependency budget is three.**
Python standard library, `pytest`, and one LLM SDK. Nothing else without asking. No agent
framework, no orchestration library, no vector database, no web UI. The rubric rewards
purposeful choices, not component count, and every dependency is a reproducibility risk.

**R5 — Offline reproduction is a first-class feature, built on day one.**
Every LLM call goes through a cassette layer that records request/response to disk. A judge
must be able to reproduce the headline numbers with **no API key, no network, no Docker**,
in under five minutes. See §5.

**R6 — Output must look hand-written.**
The generated test file is the product. It is graded (20 points) on whether the intended
user "would sign their name to it" rather than it reading as an obvious AI draft. That means:
descriptive test names, arrange/act/assert structure, no comments restating the code, no
`# This test verifies that...` preamble, no emoji, no defensive try/except padding. Same
standard for the README: plain, direct, no marketing voice.

**R7 — Ask instead of assuming.**
If a design decision is ambiguous and getting it wrong would cost hours, stop and ask.

---

## 2. What is being scored

| Criterion | Weight | What we do about it |
|---|---|---|
| Agent Solution & Engineering | 30 | One agent loop with a deterministic gate. Every component traceable to a measured failure. |
| End-to-End Quality | 20 | The output is a runnable pytest file plus an evidence report a developer would commit. |
| Problem & User Value | 15 | Developer/support engineer reproducing a reported bug. Manual time measured, not asserted. |
| Measured Improvement | 15 | Same cases, same metrics, baseline vs advanced, with the negative trade-off reported. |
| Reproducibility | 15 | `make eval-replay` from a clean environment, offline, no keys. Also a qualification gate. |
| Hot Take | 5 | Whatever the ablations actually show. Not chosen in advance. |

Tie-break order: Agent Engineering → Reproducibility → Measured Improvement → E2E Quality.

---

## 3. Repository layout

```
bugproof/
  README.md                  written last, for the judge
  REPRODUCTION.md            clean-environment guide
  CHANGELOG.md               the Improvement Changelog (micro1's 4-column format)
  PRIOR_WORK.md              what existed before the competition (see §9)
  THIRD_PARTY_NOTICES.md     attributions
  Makefile
  pyproject.toml             pinned versions
  .env.example

  src/bugproof/
    cli.py
    baseline.py              the simple baseline agent
    advanced.py              the final agent (do not create before Phase 3)
    llm.py                   LLM client + cassette record/replay layer
    sandbox.py               runs a candidate test against a case, isolated
    verdict.py               the deterministic verdict function (§4)
    trajectory.py            structured step logging
    report.py                the proof-carrying output artifact

  cases/
    <case_id>/
      report.md              the bug report the agent sees
      buggy/                 project at the broken revision
      fixed/                 same project, bug fixed
      oracle.yaml            symptom metadata + difficulty + failure family
      reference_test.py      hand-written test that MUST verify as VALID
      decoy_test.py          (some cases) red for the wrong reason; MUST be REJECTED

  eval/
    run_eval.py
    metrics.py
    harness_selftest.py

  cassettes/                 recorded LLM interactions for offline replay
  evidence/                  every eval run's raw JSON output
  trajectories/              curated agent traces for submission
  tests/                     tests for BugProof itself
```

The agent under test sees **only** `report.md` and `buggy/`. It never sees `fixed/`,
`oracle.yaml`, or `reference_test.py`. Enforce this in `sandbox.py` by copying only the
permitted paths into the working directory — do not rely on the prompt to enforce it.

---

## 4. The verdict function

This is the heart of the project. It is pure, deterministic, and contains no LLM call.

A candidate test is **VALID** for a case if and only if all five hold:

1. **Collects.** It imports and collects on `buggy/` without error.
2. **Fails on buggy.** At least one test in the file fails on `buggy/`.
3. **Fails for the reported reason.** The failure matches the symptom in `oracle.yaml` —
   exception type, message pattern, status code, or asserted value, depending on the case.
4. **Passes on fixed.** The same test passes on `fixed/`.
5. **Breaks nothing.** No test that passed on `fixed/` before adding the candidate fails
   after adding it.

Condition 3 is what separates this project from a naive fail-to-pass check.
Condition 5 stops an agent from "succeeding" by breaking the suite.

Each failed condition produces a distinct rejection reason. These reasons are the
vocabulary of the failure taxonomy and of the repair loop. Name them precisely:
`COLLECTION_ERROR`, `PASSES_ON_BUGGY`, `WRONG_SYMPTOM`, `FAILS_ON_FIXED`, `SUITE_REGRESSION`.

**Important honesty constraint.** Conditions 4 and 5 require the fix, which a real user does
not have. So the *benchmark* has the full oracle; the *agent's* gate can only check 1–3.
The README must state this plainly, and the evaluation must report **proxy precision**: of
the candidates the agent's gate accepted, what fraction the full oracle also accepts. Do not
paper over this. It is one of the more interesting results in the project.

---

## 5. Cassettes and offline replay

`llm.py` wraps every model call:

- `BUGPROOF_MODE=live` — real API call, appends to `cassettes/<run_id>.jsonl`
- `BUGPROOF_MODE=replay` — serves from cassette by hash of (model, prompt, params); errors
  loudly on a miss rather than silently calling the API

Temperature 0, fixed seeds, model version pinned and recorded in every evidence file.

The submitted zip ships the cassettes for the final baseline run and the final advanced run.
`make eval-replay` must reproduce the exact headline table with the network disabled. Verify
this by actually running it with networking off before submission.

---

## 6. Metrics

Primary metric, reported first everywhere:

- **Verified Reproduction Rate (VRR)** = valid tests / total cases.

Supporting, all on the same cases:

- **False Confident Reproduction Rate** — of the runs where the agent claimed reproduction,
  the fraction the oracle rejects. This is what the gate is built to move.
- **Claim rate** — how often the agent claimed success at all.
- **Proxy precision** — §4.
- **Rejection reason distribution** — the failure taxonomy, as counts.
- **Human time per task** — measured by the human on three cases, recorded in `evidence/`.
- **Cost per task** — tokens × published price, taken from the trajectory log.
- **Wall-clock per task**, **retries per task**.

Report absolute numbers with the fraction (`9/14`, not "64%" alone) and always report the
cost and latency the improvement bought, even when they got worse. A result that hides its
trade-off is less credible than one that names it.

---

## 7. Phases

### Phase 0 — Harness before agents

Build `sandbox.py`, `verdict.py`, `eval/`, the Makefile, and **three** cases by hand.
No LLM code yet. No agent yet.

`harness_selftest.py` must prove the harness works:
- every `reference_test.py` verifies as **VALID**
- every `decoy_test.py` verifies as **REJECTED**, with the expected rejection reason
- for at least two cases, ship a **twin decoy**: a near-copy of the reference test with one
  deliberate mutation that should flip the verdict. If the harness does not flip, the harness
  is not measuring anything.

A case whose reference test does not verify is a broken case. Fix it or delete it.

`=== STOP ===` Report: the three cases, self-test output, and the exact verdict reasons observed.

### Phase 1 — Corpus

Grow to 12–15 cases. Pure Python, small, no heavy dependencies, each installing and running
in seconds. Vary the failure families: wrong status code, off-by-one, empty-input crash,
state leaking between calls, incorrect exception type, silent wrong result, a bug that needs
two modules interacting.

Include **one deliberately hard case** and document what makes it hard — the rubric asks for
a challenging case and what it revealed.

Bug reports must read like real ones: partial, imprecise, no file paths, sometimes a stack
trace fragment, sometimes just an observed behaviour. Do not write reports that name the
function to test. That would make the task trivial and the whole comparison worthless.

`=== STOP ===` Report: case table with failure family and difficulty, full self-test green.

### Phase 2 — Baseline, then count

`baseline.py`: same model, same tools (read files, run pytest), single prompt, one attempt,
accepts any red test as done. It must be a **fair** baseline — a competent one-shot attempt,
not a crippled one. If the baseline is a strawman, the entire improvement claim collapses,
and judges will look for exactly this.

Run it on every case. Write raw results to `evidence/baseline_<timestamp>.json`.

Then produce the **failure taxonomy**: counts per rejection reason, with two or three
concrete examples quoted from real runs.

`=== STOP ===` Report: baseline VRR, claim rate, false-confident rate, taxonomy table.
**Do not propose the advanced architecture in this report.** Present the numbers.

### Phase 3 — One mechanism, chosen from the data

The human picks the dominant failure. You implement the smallest mechanism that addresses
it, and nothing else. Likely candidates, but the data decides:

| Dominant failure | Mechanism |
|---|---|
| `WRONG_SYMPTOM` | Evidence Gate — accept only if observed failure matches the reported symptom |
| `COLLECTION_ERROR` | execute-before-claim with a bounded repair loop |
| `PASSES_ON_BUGGY` | targeted retrieval before test synthesis |
| agent stops at first plausible guess | hypothesis enumeration with explicit rejection |

Bounded retries with a logged reason per retry. Re-run the same eval. Write the changelog
entry with its evidence link.

`=== STOP ===` Report: new numbers against baseline, on the same cases.

### Phase 4 — Ablations and one removal

Build the ladder, each rung measured on the same cases:

```
A  baseline
B  + execute before claiming
C  + symptom matching (Evidence Gate)
D  + bounded repair loop
E  + targeted retrieval
F  + a second reviewing agent
```

Rung F exists to be tested honestly. If it costs tokens and latency without moving VRR,
**remove it and keep the measurement** — micro1 explicitly asks for one experiment you
removed, and this is the natural place for it, since the ablation ladder produces one anyway.

The hot take is whatever the ladder shows. Do not decide it before running.

`=== STOP ===` Report: full ladder table, the removal, candidate hot takes with evidence.

### Phase 5 — Package

- `README.md`: problem → user → baseline → result → the one insight → how to reproduce.
  Architecture comes after all of that, not before. First 30 seconds must land the point.
- `REPRODUCTION.md`: exact commands, versions, expected output, runtime, cost, for both
  replay and live modes.
- `CHANGELOG.md`: micro1's four columns — Stage | What you tried and why | Evidence | Decision.
  One row per meaningful iteration, including the removed one, each linking a file in `evidence/`.
- `trajectories/`: 3–5 curated episodes, not raw dumps. Each shows agent instructions →
  action → tool response → verdict → feedback → retry → final. Include one rejection and one
  human checkpoint.
- Video script, 5 minutes: problem and baseline (0:45) → one full live run (2:00) →
  baseline vs advanced table (1:00) → biggest contributing change (0:45) → removed experiment
  and hot take (0:30).
- `make package` producing the zip: excludes `.venv`, `__pycache__`, caches; includes
  `.git`, cassettes, evidence, trajectories.

Then: unzip into a fresh directory with networking off and run `REPRODUCTION.md` verbatim.
Whatever breaks there is what the judge would have hit.

---

## 8. The output artifact

When BugProof succeeds, the user gets a test file and a short report:

```
REPRODUCTION VERIFIED

Report:    Exporting an empty invoice returns 500 instead of 422
Test:      tests/test_invoice_export.py::test_empty_invoice_returns_422
Run:       pytest tests/test_invoice_export.py -q

On the reported revision:  FAILED
  expected: HTTP 422
  observed: HTTP 500 (ValueError: max() arg is an empty sequence)

Evidence:  src/invoice/service.py:87

Attempts:  3
  1 rejected  COLLECTION_ERROR  missing fixture
  2 rejected  WRONG_SYMPTOM     failed on /invoices, report describes /invoices/export
  3 accepted  symptom matched
```

And when it fails, it says so, with the same structure and no test. A tool that reports
"could not reproduce — here is what I tried and why each attempt was rejected" is more
useful than one that guesses. Build the refusal path with the same care as the success path.

---

## 9. Prior work disclosure

`PRIOR_WORK.md` lists, with repo links and pre-competition commit dates, anything reused
from the author's earlier projects — in particular the deterministic-gate pattern
(schema validation plus set-membership evidence check) and the sandboxed subprocess
execution pattern. Rule 02 of the challenge requires this, submissions pass a plagiarism
and trace-integrity screen, and disclosed reuse is explicitly allowed. Undisclosed reuse of
your own code looks the same to a screen as copied code.

`THIRD_PARTY_NOTICES.md` credits SWT-Bench (MIT, Mündler et al., NeurIPS 2024) as the
source of the fail-to-pass formalisation, and SWE-bench (MIT) beneath it. We use the
criterion and cite the paper; we do not vendor their harness — it needs ~120 GB and Docker,
whose hardware requirements make it unsuitable for a self-contained submission.

---

## 10. Anti-goals

Do not build: a web UI, a multi-agent committee, a knowledge graph, a vector store, an
LLM-as-judge as the primary oracle, MCP servers, or a Docker-based evaluation. Do not add a
component because it is impressive. Every component must answer: *which measured failure
does this remove, and which number does it move?*

If you cannot answer that in one sentence with a file to point at, do not build it.

---

## 11. Definition of done

- `make eval-replay` reproduces the headline table offline, from a clean unzip, in under 5 minutes.
- `harness_selftest.py` is green, including twin-decoy mutations.
- Every number in the README traces to a file in `evidence/`.
- The changelog contains at least one removed experiment with its measurement.
- The generated test for the demo case is one a developer would commit without editing.
- `PRIOR_WORK.md` is complete and honest.

Start with Phase 0. Build the harness. Do not write an agent yet.
