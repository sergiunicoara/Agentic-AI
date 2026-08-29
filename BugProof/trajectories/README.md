# Curated trajectories

## Where to find the coding-agent traces

This submission contains three trace layers:

1. **Raw coding-agent session and subagent traces**
   - `traces/raw/`
   - Complete raw session/subagent transcripts copied without editing.
   - `traces/raw/INDEX.md` maps opaque agent IDs to their task and benchmark case.

2. **Curated reviewer-facing trajectories**
   - `trajectories/`
   - Short, readable summaries of representative agent episodes.
   - They link back to frozen source artifacts and include SHA-256 hashes.

3. **Runtime / benchmark evidence**
   - Baseline evidence:
     `evidence/baseline/trajectories/`
   - Advanced evidence:
     `evidence/advanced/trajectories/<case_id>/bundle.json`

The instruction document that shaped the coding agent throughout implementation
is included at the repository root:

`BUGPROOF_AGENT_BRIEF.md`

It is included so reviewers can inspect the instructions that governed the
agent's work alongside the raw traces, curated trajectories, and frozen
evaluation evidence.

## Raw coding-agent coverage

Complete raw session and subagent transcripts are included under:

`traces/raw/`

and indexed in:

`traces/raw/INDEX.md`

Every baseline attempt, candidate-generation invocation, and repair invocation
has its own raw transcript with the internal tool-call sequence captured by the
coding-agent environment. The raw trace set includes the agent's Bash, Read,
Write, and other recorded tool interactions.

The project was recorded under its working-directory name at the time,
`Micro1 Frontier Engineering Claude`, and was later named **BugProof** for the
submission. The historical paths inside the raw transcripts are intentionally
left unchanged. Case identifiers in the corresponding `.meta.json` files map
directly to the directories under `cases/`.

The curated episodes below are readable summaries and indexes over this
underlying evidence; they are not substitutes for the raw coding-agent traces.

## Frozen runtime and benchmark evidence

The advanced runs are also preserved as frozen `bundle.json` evidence for all
12 benchmark cases. These bundles contain the frozen prompt, final agent
message, execution result, gate result, and later oracle verdict where
applicable.

Start with the curated files in this directory, use `traces/raw/INDEX.md` to
inspect the original coding-agent transcripts, and follow the referenced paths
into `evidence/` for the runtime and benchmark evidence.

Six representative episodes are curated for submission: one baseline episode
plus five advanced episodes selected to show:

- a clean success;
- a mechanical execution-gate catch that bounded repair fixed;
- a repair that produced an oracle-valid candidate but was still withheld by
  the runtime gate;
- a false-confidence failure the gate did not catch;
- a structural mismatch with benchmark reference expectations.

Each curated file is an **index/explanation layer over already-frozen evidence**,
not new experimental evidence.

It does not replace, edit, or duplicate the original source artifacts it links
to. Every source file it draws from is named with its path and SHA-256 hash so
a reviewer can verify the curated summary against the original directly.

Canonical hash manifest for the frozen evaluation artifacts:

`evidence/final/integrity_hashes_after.json`

The matching files:

`evidence/final/integrity_hashes_before.json`

and:

`evidence/final/integrity_check_result.json`

show that 0 tracked frozen evaluation files changed across the submission's
final verification pass.

The raw coding-agent traces under `traces/raw/` are additional submission
evidence and are intentionally preserved byte-for-byte from their original
capture.

## Curated episodes

| # | Case | Demonstrates |
|---|---|---|
| 0 | [`baseline: discount_unit_mismatch`](00_baseline_discount_unit_mismatch.md) | One-shot baseline from exact instruction through captured tool use, candidate, claim, and later VALID oracle verdict |
| 1 | [`cart_coupon_ordering`](01_cart_coupon_ordering.md) | Straightforward successful advanced reproduction — VALID across B/C/D |
| 2 | [`roster_lookup_wrong_exception`](02_roster_lookup_wrong_exception.md) | Execution failure caught mechanically; bounded repair reaches an oracle-VALID candidate |
| 3 | [`empty_list_average_crash`](03_empty_list_average_crash.md) | Repair produces an oracle-valid candidate; runtime still withholds delivery — demonstrates abstention cost |
| 4 | [`inventory_negative_quantity`](04_inventory_negative_quantity.md) | Delivered reproduction claim later rejected as WRONG_SYMPTOM — false confidence the gate did not catch |
| 5 | [`csv_quoted_field_parsing`](05_csv_quoted_field_parsing.md) | Structural mismatch with benchmark reference expectations, unaffected by any B/C/D mechanism |

## Reading key

Each curated file distinguishes the following evidence classes explicitly.

### Raw coding-agent trace

The original captured coding-agent/subagent transcript under `traces/raw/`.
This is the authoritative source for the internal sequence of recorded tool
calls such as Read, Bash, and Write.

### Directly captured runtime evidence

This includes:

- the exact prompt sent to the runtime agent;
- the agent's full final message;
- execution results measured by the orchestrator itself through
  `sandbox.run_pytest()`;
- the deterministic gate result.

For advanced cases, these are read directly from:

`evidence/advanced/trajectories/<case_id>/bundle.json`

### Agent-authored trajectory content

Content written by the agent into project-local `trajectory.md` artifacts is
kept as agent-authored evidence. Where the same action is present in the raw
coding-agent transcript, the raw transcript can be used to verify it directly.

### Deterministic benchmark measurement

This includes the later oracle verdict produced by the deterministic benchmark
evaluator (`evaluate()`).

The benchmark oracle is evaluated separately from the runtime agent workflow.
Its result is not available to the agent and is never fed into the runtime
claim, gate, or repair decision.

This separation is important:

- raw traces show what the coding agent actually did;
- runtime evidence determines whether BugProof delivers or abstains;
- benchmark evidence determines afterwards whether the frozen candidate was
  oracle-valid.

## Trace integrity and historical paths

The raw trace files are copied into `traces/raw/` without editing. Historical
absolute paths therefore retain the original working-directory name:

`Micro1 Frontier Engineering Claude`

The submitted project is named **BugProof**. This rename does not change the
trace-to-case mapping: benchmark case identifiers in the trace metadata map
directly to `cases/<case_id>/`.

Do not interpret the historical working-directory string as a different
project; it is the name under which BugProof was implemented before the final
submission rename.

## Why the curated layer exists

The complete raw trace and evidence trees are intentionally detailed and
optimized for auditability rather than quick review.

The files in `trajectories/` provide a reviewer-facing entry point. They
highlight representative behaviors while preserving direct links back to the
raw transcripts and frozen evaluation artifacts.

The curated layer should therefore be read as an index over the evidence, not
as a replacement for it.
