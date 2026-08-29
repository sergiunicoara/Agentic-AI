# Trajectory

## What I read

- `report.md`: user ran a "merge/cleanup process" on a contact list and
  found duplicate entries remained afterward — same person, same email
  address, but typed with different capitalization in each record (one
  all lowercase, one with a capital letter). Expectation: the cleanup
  step should catch that and keep only one.

- `buggy/contacts.py`: the only file in `buggy/`. It defines a single
  function, `unique_emails(entries)`, which is the "cleanup" step the
  report refers to. It deduplicates a list of entry dicts by their
  `"email"` key using a `set()` of seen emails, keeping the first
  occurrence of each. Critically, it compares `email` values as-is
  (`if email not in seen`), with no normalization (no `.lower()`,
  `.casefold()`, or similar) before the membership check or insertion
  into the `seen` set.

## What I concluded

Because Python string equality (and set membership) is case-sensitive,
`"jane.doe@example.com"` and `"Jane.Doe@example.com"` are treated as two
distinct emails by `unique_emails`. Two entries for the same person whose
email differs only in capitalization will both be kept in the result,
which is exactly the duplicate-survives-cleanup behavior described in
report.md.

## What happened when I ran the test

I wrote `candidate_test.py` (in the working directory, importing
`from contacts import unique_emails`, matching how it will be run once
copied next to `contacts.py`). The test builds two entries for "Jane
Doe" with emails `jane.doe@example.com` and `Jane.Doe@example.com`,
calls `unique_emails`, and asserts exactly one result survives with the
lowercase email.

Per the task instructions, I copied `candidate_test.py` into `buggy/`,
ran `python -m pytest candidate_test.py -v` from inside `buggy/`, and
observed:

```
candidate_test.py::test_unique_emails_dedupes_case_insensitively FAILED

    assert len(result) == 1
E   AssertionError: assert 2 == 1
E    +  where 2 = len([{'email': 'jane.doe@example.com', ...}, {'email': 'Jane.Doe@example.com', ...}])

1 failed in 1.40s
```

The test failed exactly as expected given the bug: `unique_emails`
returned both entries instead of collapsing them to one, confirming the
case-sensitivity dedup bug described in report.md.

I then removed the temporary copy (`buggy/candidate_test.py`) along with
the `__pycache__`/`.pytest_cache` directories that pytest generated
during the run, restoring `buggy/` to contain only the original,
untouched `contacts.py`. The real `candidate_test.py` remains only in
the working directory (sibling of `report.md` and `buggy/`).

## Files read / commands run:

- Read `report.md`
- Read `buggy/contacts.py`
- Wrote `candidate_test.py` in the working directory
- Ran: `cp candidate_test.py buggy/candidate_test.py`
- Ran (from `buggy/`): `python -m pytest candidate_test.py -v` — observed 1 failed (AssertionError: assert 2 == 1)
- Ran: `rm buggy/candidate_test.py`
- Ran: `rm -rf buggy/__pycache__ buggy/.pytest_cache` (cleanup of pytest-generated artifacts)
- Verified `buggy/` contains only `contacts.py` afterward
