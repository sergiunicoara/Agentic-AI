# Trajectory

Read `report.md`: a user reports that after running the merge/cleanup process,
duplicate contacts remain when the same email address appears with different
capitalization (e.g. one lowercase, one with a capital letter). They expect
the cleanup to treat these as the same contact and keep only one.

Inspected `buggy/contacts.py`, the only source file present. It contains a
single function `unique_emails(entries)` that deduplicates a list of contact
dicts by their `"email"` field, using a `set()` of emails seen so far and an
`in` check to decide whether to keep each entry. The email strings are used
as-is, with no normalization (no `.lower()`/`.casefold()`), so `"Jane.Doe@example.com"`
and `"jane.doe@example.com"` are treated as two distinct keys in the `seen`
set and both entries survive into the result. This exactly matches the
reported symptom: case-differing duplicates are not merged.

Wrote `candidate_test.py` (in the working directory, importing `from
contacts import unique_emails` per the stated execution setup) with a test
that feeds two entries for "Jane Doe" whose emails differ only in
capitalization, and asserts that `unique_emails` collapses them to a single
result entry.

Per instructions, ran the one allowed verification: copied
`candidate_test.py` into `buggy/`, ran `pytest` from there. The test failed
as expected — `assert len(result) == 1` failed with `assert 2 == 1`, i.e.
both case-variant entries were kept, confirming the reproduction of the bug.
Removed the temporary copy and the `__pycache__`/`.pytest_cache` artifacts
created by the test run afterward, leaving `buggy/contacts.py` byte-for-byte
unchanged (313 bytes, original timestamp preserved) and `candidate_test.py`
present only in the working directory alongside `report.md`.
