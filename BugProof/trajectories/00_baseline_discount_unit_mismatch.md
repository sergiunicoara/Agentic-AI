# Baseline trajectory — discount_unit_mismatch

**Purpose:** representative trajectory for the one-shot baseline agent (A). This
case is included because its raw subagent JSONL transcript survived and can be
audited from instruction through tool use to final claim.

## Original frozen sources

- `evidence/baseline/trajectories/discount_unit_mismatch_transcript.jsonl`  
  SHA-256: `a5464ee03a6ac1c36026bd34ddf51c18fdd18cf1a972725ed74a9de9080e734f`
- `evidence/baseline/trajectories/discount_unit_mismatch_trajectory.md`  
  SHA-256: `f5cc55ced9884d42d9f843445ea14eb048dc26b2368ab8b2ff499e519247859c`
- `evidence/baseline/candidates/discount_unit_mismatch/candidate_test.py`  
  SHA-256: `61e3cbcfebc9ecb8f8385be53ed7d5278aae241d989242fd44e27d7faeb9db6b`
- `evidence/baseline/results.json`  
  SHA-256: `819df1c97b85ea50354f939eeaed8491c0f873545284ec02d15a4126918ce211`
- `evidence/baseline/result_table.json`  
  SHA-256: `5a8afd13058e5c54ca9a203669cdab08414bb3af0e4df232dd2f05e2c78bda2a`

The complete frozen-artifact manifest is also available at
`evidence/final/integrity_hashes_after.json`.

## Agent instruction — directly captured

The baseline agent was given only a working directory containing `report.md`
and `buggy/`. It was instructed to:

1. read the bug report;
2. inspect only the buggy repository;
3. create one `candidate_test.py`;
4. leave `buggy/` unchanged;
5. optionally execute the candidate exactly once;
6. write a short trajectory;
7. finish with `CLAIM: REPRODUCED` or `CLAIM: NOT_REPRODUCED`;
8. make no revision after feedback, because no feedback would be provided.

The exact prompt is the first record in the frozen JSONL transcript above.

## What the agent inspected — directly captured

The transcript records the agent reading `report.md` and inspecting
`buggy/pricing.py`:

```python
def apply_discount(price, percent_off):
    """Return the price after applying a percentage discount."""
    return price - (price * percent_off)
```

The report described a `$100` item with a `20%-off` code producing roughly
`-$1900` instead of `$80` while no-discount checkout worked normally.

## Agent reasoning — agent-authored / self-reported

The agent concluded that `percent_off` was being treated as a fraction even
though the observed caller behavior used whole-number percentages. It reasoned:

```text
apply_discount(100, 20)
= 100 - (100 * 20)
= -1900
```

which directly matched the observed report.

The agent wrote a candidate with two assertions, including the reported example:

```text
apply_discount(100, 20) == 80
```

The exact frozen test is in
`evidence/baseline/candidates/discount_unit_mismatch/candidate_test.py`.

## Tool execution — directly captured

The raw transcript captures the agent's file reads/writes and its one permitted
pytest verification. The agent reported both candidate assertions failing on the
buggy implementation, including:

```text
-1900 == 80
-450 == 45
```

It then removed the temporary copied test and generated cache, leaving the buggy
source unchanged.

## Final agent claim — directly captured

The final response ends with:

```text
CLAIM: REPRODUCED
```

and explains that the test reproduces the same magnitude and mechanism reported
by the user.

## Deterministic benchmark measurement — separate, later

The oracle evaluation was not available to the baseline agent. After the
candidate was frozen, `evidence/baseline/results.json` records:

```text
case_id: discount_unit_mismatch
status: VALID
reason: null
detail: all five conditions satisfied
```

`evidence/baseline/result_table.json` additionally records:

```text
claimed_reproduced: true
oracle_verdict: VALID
latency_seconds: 39.4
tokens: 49268
tool_uses: 7
```

## What this episode demonstrates

This is a clean baseline success: the one-shot agent had only the bug report and
buggy source, generated a runnable regression candidate, verified that it failed
on the buggy implementation for the reported behavior, claimed reproduction,
and the later deterministic oracle classified the frozen candidate as `VALID`.

## Evidence boundaries

- The raw JSONL transcript is directly captured and preserved.
- `trajectory.md` is agent-authored and therefore self-reported reasoning.
- The oracle verdict is a deterministic measurement performed separately after
  the candidate was frozen.
- No oracle/fixed/reference-test feedback was available to the baseline agent.
