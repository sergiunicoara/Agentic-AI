# Trajectory

## What changed and why

The prior candidate asserted `len(fields) == 3` where `3` was justified only
by an inline comment claiming "there are exactly two REAL (unquoted,
field-separating) commas in this line" -- a hand-count of the crafted
literal `line` string that is not itself a test setup constant and is not
supported by any quoted text in report.md. The evidence check correctly
flagged this: the equality's BASIS effectively used an ungrounded operand
(the claimed "2 real delimiters").

Fix: restructured the test so the expected field count is *computed*, not
hand-counted. The line is now built by joining three explicit Python
variables (`id_field`, `description_field`, `price_field`) with the
delimiter, and `expected_field_count = len(setup_fields)` where
`setup_fields = [id_field, description_field, price_field]`. This makes the
expected value `3` a directly re-computable arithmetic fact about the test's
own setup data (a list literal with 3 elements), not an inference about
comma-counting inside a raw string. The correctness rule that justifies
treating `description_field` as a single field is grounded in
`parse_line`'s own docstring in `buggy/linefmt.py`: "Split a single
delimited line into fields, respecting double-quoted fields." -- since
`description_field` is wrapped in quotes in `line`, that contract requires
it to survive as one field regardless of the delimiter character or
embedded quoted phrase inside it.

The rest of the test's logic (the bug mechanism description, and the three
substring assertions on `fields[1]`) was left as-is; it was not implicated
in the flagged gap and matches the actual buggy behavior traced by hand
below.

## What was observed

Hand-traced `parse_line` over
`line = '101,"He said "ok, sure" today",29.99'` against
`buggy/linefmt.py`: the `in_quotes` flag toggles on every literal `"`,
so the embedded phrase's two quote characters (`"ok, sure"`) each flip
`in_quotes` again. This makes the flag `False` exactly while scanning past
the comma inside `"ok, sure"`, so that comma is treated as a real
delimiter and splits the field early. Result on buggy code:
`['101', 'He said ok', ' sure today', '29.99']` (4 fields, embedded quote
characters dropped) -- confirmed by running the revised test (see below),
which reports `AssertionError: assert 4 == 3` at the `len(fields) ==
expected_field_count` line, with pytest's own diff showing
`4 = len(['101', 'He said ok', ' sure today', '29.99'])`. This matches
report.md's description exactly: the embedded quote marks are gone from
the value, and the field boundary shifted right after that point.

Test execution (one run, as required): copied `candidate_test.py` into
`buggy/` as `test_candidate_tmp.py`, ran `python -m pytest
test_candidate_tmp.py -v` from inside `buggy/`, observed 1 failed test
(the AssertionError above), then deleted the temp copy and the
`__pycache__` / `.pytest_cache` directories created by the run so
`buggy/` is restored to containing only `linefmt.py`, byte-for-byte
unchanged.

## Files read / commands run:

- Read: `report.md`
- Read: `buggy/linefmt.py`
- Bash: `find buggy -type f` (initial contents check)
- Bash: `cp candidate_test.py buggy/test_candidate_tmp.py && cd buggy && python -m pytest test_candidate_tmp.py -v ... && rm buggy/test_candidate_tmp.py && ls buggy/`
- Bash: `rm -rf __pycache__ .pytest_cache` inside `buggy/` (cleanup of artifacts created by the test run)
- Bash: `find . -maxdepth 2` (final state verification of the repair/ directory)
- Write: overwrote `candidate_test.py` with the revised test
- Write: this file (`trajectory.md`)
