# Trajectory: repair of empty_list_average_crash candidate

## What changed and why

The original candidate wrapped `average_score([])` in
`pytest.raises(ZeroDivisionError)`. That is the *current buggy behavior*,
not the *desired* behavior, so on `buggy/` the exception is raised, caught
by `pytest.raises`, and the test **passes** — it can never fail on buggy/,
which is exactly what the orchestrator observed
(`EXECUTION_FAILURE reason=NO_FAILURE_OBSERVED ... candidate collected and
passed on buggy/`).

A regression test must fail on the buggy code and (presumably) pass once
fixed. The fix inverts the assertion: call `average_score([])` as a plain
statement, with no `pytest.raises` guard. If the implementation still
raises `ZeroDivisionError`, the exception propagates out of the test body
and pytest reports a failure. If a future fix makes `average_score([])`
return anything without raising, the test passes.

I deliberately did **not** pin an exact expected return value (e.g.
`== 0`). `report.md` only describes the crash itself ("Stack trace points
into the stats helper somewhere, ZeroDivisionError ... trying to average
scores before any exist") and never states what the fixed function should
return instead. The phrase "returning something sane like 0" that appeared
in the original candidate's docstring was invented by whoever wrote that
candidate, not sourced from report.md, so asserting `== 0` would be an
ungrounded literal. Per the repair instructions, since I can't ground that
exact value, I narrowed the assertion to only what report.md actually
supports: that calling `average_score` on an empty list must not raise
`ZeroDivisionError`.

## What I observed

- `buggy/stats.py` (only file in `buggy/`):
  ```python
  def average_score(scores):
      """Return the mean of a list of numeric scores."""
      return sum(scores) / len(scores)
  ```
  For `scores = []`, `sum([]) == 0` and `len([]) == 0`, so it evaluates
  `0 / 0`, which raises `ZeroDivisionError: division by zero` in Python.
  This matches report.md's description exactly (crash on a brand-new quiz
  with no scores yet, ZeroDivisionError, in the averaging helper).

- Ran the revised test once: copied `candidate_test.py` into
  `buggy/test_candidate_temp.py`, ran
  `python -m pytest test_candidate_temp.py -v` from inside `buggy/`,
  then deleted the temp file (and the `__pycache__` directory pytest
  generated) so `buggy/` is restored byte-for-byte.

  Result: **FAILED**. Traceback:
  ```
  >       average_score([])
  ...
      def average_score(scores):
          """Return the mean of a list of numeric scores."""
  >       return sum(scores) / len(scores)
  E       ZeroDivisionError: division by zero
  stats.py:3: ZeroDivisionError
  ```
  This confirms the test now genuinely fails on `buggy/`, and fails for
  the reported reason (ZeroDivisionError raised from the average helper
  when scores is empty) rather than passing vacuously.

## Files read / commands run

- Read: `report.md`
- Read: `buggy/stats.py`
- Wrote: `candidate_test.py` (overwritten with revised test)
- Ran: `cp candidate_test.py buggy/test_candidate_temp.py`
- Ran: `cd buggy && python -m pytest test_candidate_temp.py -v`
- Ran: `rm buggy/test_candidate_temp.py`
- Ran: `rm -rf buggy/__pycache__` (cleanup of pytest-generated cache so
  `buggy/` matches its original state)
- Ran: `ls -la buggy/` to confirm only `stats.py` remains

## EVIDENCE

- KIND: literal
  ITEM: exception contract asserting no ZeroDivisionError is raised by average_score([])
  QUOTE (report.md): "Stack trace points into the stats helper somewhere, ZeroDivisionError. My guess is it's trying to average scores before any exist."
  QUOTE (buggy/stats.py): "return sum(scores) / len(scores)"
  NOTE: report.md establishes the crash (ZeroDivisionError from the averaging helper on empty input) as the bug being reported; buggy/stats.py's `sum([]) / len([])` is the literal `0/0` that produces it. The test asserts this crash no longer occurs, without inventing a specific replacement return value that report.md never specifies.

END_EVIDENCE

CLAIM: VERIFIED_REPRODUCTION

The revised test calls `average_score([])` as a bare statement (no `pytest.raises` guard), so it fails on `buggy/` precisely because `sum([])/len([])` raises `ZeroDivisionError` — confirmed by actually running it once against a temp copy in `buggy/`, which produced a FAILED result with that exact exception and traceback into `stats.py:3`. The assertion is grounded entirely in verbatim material: report.md's own description of the crash (new quiz, no scores yet, ZeroDivisionError in the stats helper) and the literal division-by-zero expression in `buggy/stats.py`. No exact replacement value (like the earlier candidate's "0") is asserted, since report.md never states what the fixed function should return — only that it should not crash the way it currently does. `buggy/` was left byte-for-byte unchanged: the temp test file and the `__pycache__` directory generated during the single test run were both removed afterward, leaving only the original `stats.py`.
