---
description: "Run golden dataset evaluation and print metrics table"
context: fork
tools:
  - Bash
  - Read
---

# /run-evals

Run the evaluation suite against the golden dataset and report per-domain accuracy.

## Usage
```
/run-evals
/run-evals --dataset evaluation/golden_dataset.jsonl
/run-evals --filter severity=P1
```

## What it measures (D5.5 — stratified sampling, not just aggregate accuracy)
- Per-severity accuracy (P1/P2/P3/P4) — aggregate masks poor P1 performance
- Field-level calibration: root_cause, severity, confidence, next_steps
- Escalation threshold adherence (D5.2)
- Provenance completeness (D5.6)

## Steps
Run: `python evaluation/judge.py $ARGUMENTS`
