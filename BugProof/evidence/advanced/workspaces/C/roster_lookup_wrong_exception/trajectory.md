# Trajectory

## What I read

- `report.md`: a support ticket says looking up a member by id "sometimes
  throws an unhandled error and the request fails hard instead of giving a
  normal 'member not found' response." It only happens for ids that don't
  exist in the roster; ids that do exist work fine. The logged error is
  `IndexError: list index out of range`.

- `buggy/roster.py` (full file, 5 lines):

  ```python
  def find_member(members, member_id):
      """Return the member record with the given id."""
      matches = [m for m in members if m["id"] == member_id]
      return matches[0]
  ```

## What I concluded

`find_member` filters `members` into `matches` for entries whose `"id"`
equals `member_id`, then unconditionally returns `matches[0]`. If no member
has that id, `matches` is an empty list, and `matches[0]` raises
`IndexError: list index out of range` — exactly the error and exact message
quoted in report.md. This matches the reported behavior precisely: lookups
of an id that exists return the correct record (matches has one element,
`matches[0]` works), while lookups of a nonexistent id raise an unhandled
`IndexError` instead of returning some "not found" sentinel/exception the
caller could handle.

## Test written

`candidate_test.py` (in the working directory, sibling of `report.md` and
`buggy/`) imports `from roster import find_member` (flat import, since the
test will be copied alongside `roster.py` when run). It has one test with
two parts:

1. `find_member(members, 1)` for an id that exists — asserts it returns the
   matching record, confirming the "existing ids work fine" part of the
   report.
2. `find_member(members, 999)` for an id that does not exist — wrapped in
   `pytest.raises(IndexError)`, confirming the "unhandled IndexError for
   missing ids" bug from the report.

## What happened when I ran it

Per the task instructions, I copied `candidate_test.py` into `buggy/`,
ran `python -m pytest candidate_test.py -v` from inside `buggy/`, and then
deleted the temporary copy (plus the `__pycache__`/`.pytest_cache`
directories pytest created) from `buggy/`, leaving `buggy/roster.py`
byte-for-byte unchanged.

Observed output:

```
collecting ... collected 1 item

candidate_test.py::test_find_member_missing_id_raises_indexerror_not_handled PASSED [100%]

============================== 1 passed in 0.32s ==============================
```

The test passed, meaning both assertions held: the existing-id lookup
returned the correct record, and the missing-id lookup did in fact raise
`IndexError` (uncaught), reproducing the bug described in report.md.

## Files read / commands run:

- Read `report.md`
- Read `buggy/roster.py`
- Wrote `candidate_test.py` in the working directory
- `cp candidate_test.py buggy/candidate_test.py`
- `cd buggy && python -m pytest candidate_test.py -v`
- `rm buggy/candidate_test.py`
- `rm -rf buggy/__pycache__ buggy/.pytest_cache` (cleanup of pytest-generated artifacts)
- `ls -la buggy` (confirmed only `roster.py` remains, unmodified)
