# Trajectory

Read report.md: a user hit a crash on a newly created quiz that no one had
taken yet, with a ZeroDivisionError in the stats helper, suspected to come
from averaging scores before any exist.

Inspected buggy/stats.py, which contains a single function:

```python
def average_score(scores):
    """Return the mean of a list of numeric scores."""
    return sum(scores) / len(scores)
```

`sum(scores) / len(scores)` divides by `len(scores)` unconditionally. When
`scores` is an empty list (the exact "quiz with no submissions yet" case
described in the report), `len(scores)` is 0 and Python raises
`ZeroDivisionError: division by zero`. This matches the report precisely:
no guard exists for the empty-list case.

Wrote candidate_test.py (in the working directory, importing `from stats
import average_score` per the stated execution setup) asserting that
`average_score([])` returns 0 instead of raising, expressing the
reasonable expectation that a quiz with no scores yet should report a
sane default rather than crash.

Verified per instructions: copied candidate_test.py into buggy/, ran
`pytest candidate_test.py -v` from buggy/. The test failed with
`ZeroDivisionError: division by zero` at `stats.py:3`, i.e. it fails
specifically because of the reported defect (not for an unrelated
reason like an import error). Removed the temporary copy and pytest
cache artifacts from buggy/ afterward; buggy/ now contains only the
original stats.py, unchanged.
