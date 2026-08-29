# Trajectory

Read `report.md`: a support ticket says looking up a member by id sometimes throws
an unhandled `IndexError: list index out of range` instead of a normal "member not
found" response, and only for ids that are not present in the roster.

Read `buggy/roster.py`. It contains a single function:

```python
def find_member(members, member_id):
    """Return the member record with the given id."""
    matches = [m for m in members if m["id"] == member_id]
    return matches[0]
```

The cause is clear: `matches` is built by filtering for the given id, and the code
unconditionally returns `matches[0]`. When no member has that id, `matches` is an
empty list, so `matches[0]` raises `IndexError: list index out of range` — exactly
the error from the bug report. This matches the reported symptom precisely (works
fine for existing ids, blows up only for missing ones).

The function is named `find_member` (not `get_member`/`require_member`), which is
the conventional Python "find" idiom (like `str.find`, `dict.get`) of returning
`None` when nothing matches rather than raising. That is the "normal not found
response" a caller would expect instead of an unhandled exception, so the test
asserts `find_member` returns `None` for a missing id (both on a non-empty roster
and on an empty roster), plus a sanity check that an existing id still returns the
correct record.

Wrote `candidate_test.py` in the working directory with three tests. Verified by
temporarily copying it into `buggy/` and running `pytest` from there:
- `test_find_member_returns_existing_member` PASSED.
- `test_find_member_missing_id_does_not_raise_indexerror` FAILED with
  `IndexError: list index out of range`, raised from `roster.py:4`, matching the
  report exactly.
- `test_find_member_missing_id_on_empty_roster` FAILED the same way.

After confirming the failure, removed the temporary copy (and the `__pycache__`/
`.pytest_cache` artifacts created by the run) from `buggy/`, leaving it byte-for-byte
as it started. The final `candidate_test.py` lives only in the working directory,
importing via `from roster import find_member` as required.
