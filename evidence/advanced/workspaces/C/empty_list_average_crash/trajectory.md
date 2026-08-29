# Trajectory

## What I read

- `report.md`: describes a crash reported by a user who had "just created a
  new quiz" and "hadn't had anyone take it yet." The stack trace pointed
  into "the stats helper" with a `ZeroDivisionError`. The reporter's guess
  is that it's "trying to average scores before any exist."
- `buggy/stats.py`: contains a single function,
  `average_score(scores)`, whose body is `return sum(scores) / len(scores)`.
  With `scores == []`, `sum([])` is `0` and `len([])` is `0`, so the
  division `0 / 0` raises `ZeroDivisionError` in Python. This matches the
  report exactly: a brand-new quiz with zero submissions has an empty
  scores list, and calling `average_score` on it divides by zero.

## What I concluded

The bug is a straightforward unguarded division by `len(scores)` in
`average_score`, with no check for an empty list. Calling
`average_score([])` reproduces the reported `ZeroDivisionError`.

## Test written

`candidate_test.py` (working directory root) imports `average_score` from
`stats` (flat import, matching how it will be run once copied alongside
`stats.py`) and asserts that `average_score([])` raises
`ZeroDivisionError` via `pytest.raises(ZeroDivisionError)`.

## What happened when I ran it

Per instructions, I temporarily copied `candidate_test.py` into `buggy/`,
ran `python -m pytest candidate_test.py -v` from inside `buggy/`, and then
deleted the temporary copy (and the `__pycache__`/`.pytest_cache`
directories pytest created) so `buggy/` is back to containing only the
original `stats.py`, byte-for-byte unmodified.

Observed output:

```
collected 1 item

candidate_test.py::test_average_score_empty_list_raises_zero_division_error PASSED [100%]

============================== 1 passed in 0.31s ==============================
```

The test passed, confirming that `average_score([])` does in fact raise
`ZeroDivisionError` against the current `buggy/stats.py`, reproducing the
behavior described in `report.md`.

## Files read / commands run:

- Read `report.md`
- Read `buggy/stats.py`
- Wrote `candidate_test.py` in the working directory
- Ran: `cp candidate_test.py buggy/candidate_test.py`
- Ran (from `buggy/`): `python -m pytest candidate_test.py -v`
- Ran: `rm buggy/candidate_test.py`
- Ran: `rm -rf buggy/__pycache__ buggy/.pytest_cache` (cleanup of pytest-generated artifacts to restore `buggy/` to its original byte-for-byte state)
- Ran: `ls -la buggy` and `ls -la .` to confirm final directory state
