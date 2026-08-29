# Trajectory

Read `report.md`: users are seeing handles with double/triple underscores
(e.g. "jane___doe") when their display name has extra spaces between words
at signup (e.g. "Jane  Doe" typed with two spaces).

Inspected `buggy/handles.py`, which contains a single function:

```python
def normalize_handle(raw):
    return raw.strip().lower().replace(" ", "_")
```

`str.replace(" ", "_")` replaces every individual space character with an
underscore, so it does not collapse runs of consecutive spaces — two spaces
become two underscores, three spaces become three underscores, etc. This
exactly matches the reported symptom: "Jane  Doe" (two spaces) normalizes to
"jane__doe" instead of the expected "jane_doe". A correct implementation
would need to collapse runs of whitespace (e.g. via `re.sub(r"\s+", "_",
...)`) before/instead of a plain single-character replace.

Wrote `candidate_test.py` with three cases: two spaces collapsing to one
underscore, many extra spaces collapsing to one underscore, and a baseline
single-space case that should already pass. Per the one-shot verification
step, copied it into `buggy/`, ran `pytest` there, and observed:

- `test_multiple_spaces_collapse_to_single_underscore`: FAILED (`jane__doe` != `jane_doe`)
- `test_many_extra_spaces_still_collapse`: FAILED (`jane_____doe` != `jane_doe`)
- `test_single_space_still_works`: PASSED

This confirms the test reproduces the defect described in the report. The
temporary copy and generated `__pycache__` were then removed from `buggy/`,
leaving it byte-for-byte as it started (only `handles.py`).
