# Trajectory

## What changed and why

The evidence check flagged both assertions (`assert result == "jane_doe"`)
as NOT GROUNDED: the exact string `"jane_doe"` (single underscore, the
*desired* fixed output) is never quoted verbatim anywhere in report.md.
report.md quotes only the broken example `"jane___doe"` and otherwise
describes the correct form qualitatively, as "the usual single-underscore
style everyone else has." Since `normalize_handle`'s arithmetic is string
manipulation (not numeric), this value cannot be grounded as `derived`
either — the gate's arithmetic evaluator only handles numbers.

Per the repair instructions, I narrowed both assertions to something I can
honestly ground: that the output contains no run of two-or-more
underscores (`"__" not in result`). This is a direct, checkable consequence
of report.md's own qualitative description of correct handles ("the usual
single-underscore style"), without inventing or pinning an exact "correct"
string that was never quoted.

I did not change the inputs (`"Jane  Doe"`, `"Jane   Doe"`) or the overall
structure/intent of the two tests -- only the final assertion in each.

## What I observed

Read `buggy/handles.py`:
```
def normalize_handle(raw):
    """Turn free-form display text into a canonical @handle."""
    return raw.strip().lower().replace(" ", "_")
```
`.replace(" ", "_")` substitutes every individual space character with its
own underscore, so N consecutive spaces become N consecutive underscores
rather than collapsing to one. This matches report.md's description of the
bug exactly.

Traced by hand and confirmed by the test run:
- `normalize_handle("Jane  Doe")` (2 spaces) -> `"jane__doe"` (2 underscores)
- `normalize_handle("Jane   Doe")` (3 spaces) -> `"jane___doe"` (3 underscores)

Notably, the triple-space case reproduces report.md's own quoted example
`"jane___doe"` character-for-character, which is strong corroboration that
this is the same bug the report describes.

## Test run (required, performed exactly once)

Copied `candidate_test.py` into `buggy/` as `test_candidate_run.py`, ran
`python -m pytest test_candidate_run.py -v` from inside `buggy/`, recorded
output, then deleted the temp copy (and the `__pycache__` directory pytest
created) so `buggy/` is left byte-for-byte as it was.

Result: both tests FAILED against buggy/, as expected for a regression
test that reproduces the bug:
- `test_double_space_produces_single_underscore`: `AssertionError: assert '__' not in 'jane__doe'`
- `test_triple_space_produces_single_underscore`: `AssertionError: assert '__' not in 'jane___doe'`

This is "2 failing testcase(s) observed on buggy/" -- consistent with (and
now correctly grounded relative to) the orchestrator's prior observation.

## Files read / commands run

- Read: `report.md`
- Read: `buggy/handles.py`
- Read: `candidate_test.py` (original, before revision)
- Wrote: `candidate_test.py` (revised)
- Ran: `cp candidate_test.py buggy/test_candidate_run.py`
- Ran: `python -m pytest test_candidate_run.py -v` (from within `buggy/`), output captured
- Ran: `rm -f buggy/test_candidate_run.py` (removed temp copy)
- Ran: `rm -rf buggy/__pycache__` (removed pytest cache byproduct, restoring `buggy/` to its original contents)
