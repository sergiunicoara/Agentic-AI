# Trajectory

## What I read

- `report.md`: describes that new account handles sometimes have double or
  triple underscores (e.g. `jane___doe`) instead of the usual single
  underscore, and that this seems to happen when a display name has extra
  spaces between words at signup (e.g. "Jane  Doe" typed with two spaces
  instead of one).
- `buggy/handles.py`: contains a single function,
  `normalize_handle(raw)`, implemented as
  `raw.strip().lower().replace(" ", "_")`.

## What I concluded

`str.replace(" ", "_")` replaces every individual space character with an
underscore — it does not collapse runs of consecutive spaces into a single
underscore. So an input like `"Jane  Doe"` (two spaces) has each of its two
space characters replaced independently, producing `"jane__doe"` (two
underscores), and `"Jane   Doe"` (three spaces) produces `"jane___doe"`
(three underscores) — matching the exact string quoted in the bug report.
This is a straightforward root-cause match for the reported behavior: extra
spaces in the display name at signup directly translate into extra
underscores in the resulting handle, one underscore per space character,
rather than being collapsed to a single separator.

## What happened when I ran the test

I wrote `candidate_test.py` in the working directory with two tests:
1. `test_double_space_produces_single_underscore` — calls
   `normalize_handle("Jane  Doe")` and asserts the result equals
   `"jane_doe"`.
2. `test_triple_space_produces_single_underscore` — calls
   `normalize_handle("Jane   Doe")` and asserts the result equals
   `"jane_doe"`.

Per the task instructions, I copied `candidate_test.py` into `buggy/`,
ran `python -m pytest candidate_test.py -v` from inside `buggy/`, and
observed:

```
candidate_test.py::test_double_space_produces_single_underscore FAILED
candidate_test.py::test_triple_space_produces_single_underscore FAILED

AssertionError: assert 'jane__doe' == 'jane_doe'
AssertionError: assert 'jane___doe' == 'jane_doe'

2 failed in 1.17s
```

Both tests failed with the exact bug behavior described in the report: two
spaces produced `jane__doe` (double underscore) and three spaces produced
`jane___doe` (triple underscore, matching the literal string quoted in
`report.md`). This confirms the reproduction.

After running, I deleted the temporary copy of `candidate_test.py` from
`buggy/` along with the `__pycache__` and `.pytest_cache` directories pytest
created there, so `buggy/` is restored to its original state (only
`handles.py`, byte-for-byte unchanged). The real `candidate_test.py` remains
only in the working directory (sibling of `report.md` and `buggy/`).

## Files read / commands run:

- Read `report.md`
- Read `buggy/handles.py`
- Wrote `candidate_test.py` in the working directory
- Ran: `cp candidate_test.py buggy/candidate_test.py`
- Ran: `cd buggy && python -m pytest candidate_test.py -v` (observed 2 failed,
  as quoted above)
- Ran: `rm buggy/candidate_test.py`
- Ran: `rm -rf buggy/__pycache__ buggy/.pytest_cache`
- Ran: `ls -la buggy/` to confirm only `handles.py` remains
