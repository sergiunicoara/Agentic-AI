# Trajectory

## What I read

- `report.md`: a product-catalog import mangled one description field.
  The field had "a quoted phrase inside it"; after import the embedded
  quote marks were gone from the value, and the field boundary appeared
  to shift right after that point. Most rows import fine, so it's
  specific to this kind of field (an embedded quoted phrase, not just
  any quote).

- `buggy/linefmt.py`: a 15-line `parse_line(line, delimiter=",")`
  function. It walks the line character by character, keeping an
  `in_quotes` boolean that is *flipped* on every `"` character
  encountered (`if ch == '"': in_quotes = not in_quotes`). A delimiter
  character only starts a new field when `not in_quotes`. Quote
  characters themselves are never appended to the field buffer — they
  only ever toggle the flag.

## What I concluded

The flag is toggled on *every* individual `"` character with no notion
of doubled/escaped quotes (`""`) or of "a quote that is part of the
field's content rather than the field's own delimiter". So when a field
that is already double-quoted (because it contains the delimiter)
additionally contains an embedded quoted phrase, each of that phrase's
two quote characters flips `in_quotes` again. Depending on how many
quote characters have been seen by the time a real delimiter inside the
phrase is reached, the parser can end up thinking it is "outside"
quotes at exactly that point, and split the field there — this is the
"field boundary shifted somehow right after that point" symptom. In all
cases the quote characters themselves are dropped (never copied into
`current`), matching "the embedded quote marks are just gone".

I verified this by hand-tracing the toggle sequence for
`101,"He said "ok, sure" today",29.99` and then actually running it
through the real `parse_line` function (via a throwaway `python -c`
snippet, not part of the committed test) before writing the test:

```
>>> parse_line('101,"He said "ok, sure" today",29.99', ',')
['101', 'He said ok', ' sure today', '29.99']
```

This is a clean, minimal illustration of both symptoms at once: the
quotes around `"ok, sure"` are gone from the output, and the comma
inside that embedded phrase incorrectly acts as a field separator,
producing 4 fields instead of the correct 3 (id, description, price) —
i.e. the field boundary shifts right after the embedded quoted phrase.
I also confirmed the "should" behavior baseline: a quoted field
containing the delimiter but *no* embedded quoted phrase parses
correctly as a single field
(`parse_line('101,"He said ok, sure today",29.99', ',')` →
`['101', 'He said ok, sure today', '29.99']`), which is consistent
with the docstring's promise to respect double-quoted fields, and
confirms the embedded quoted phrase is what triggers the bug —
matching "Most rows in the file import fine — it seems specific to
this kind of field."

## Test written

`candidate_test.py` (in the working directory, sibling of `report.md`
and `buggy/`), importing `from linefmt import parse_line`. It builds
the line above and asserts:
- `len(fields) == 3` (2 real unquoted delimiters + 1, per the
  docstring's "respecting double-quoted fields" rule)
- the description text (`"He said"`, `"sure"`, `"today"`) all remain
  inside a single field (`fields[1]`), i.e. the comma inside the
  embedded quoted phrase did not split the field.

## What happened when I ran it (required one-time check)

Copied `candidate_test.py` into `buggy/`, ran
`python -m pytest candidate_test.py -v` from inside `buggy/`.

Result: **1 failed**.

```
>       assert len(fields) == 3
E       AssertionError: assert 4 == 3
E        +  where 4 = len(['101', 'He said ok', ' sure today', '29.99'])
```

This is exactly the reported bug: the parser produced 4 fields instead
of 3, splitting `'He said ok, sure today'` into `'He said ok'` and
`' sure today'` — the embedded quote marks around `ok, sure` are gone
and the field boundary shifted right at that point.

After observing this failure, I removed the temporary copy
(`buggy/candidate_test.py`) plus any `__pycache__`/`.pytest_cache`
artifacts pytest created under `buggy/`, and confirmed `buggy/` again
contains only the original `linefmt.py` (474 bytes, untouched). The
real `candidate_test.py` remains only in the working directory.

## Files read / commands run:

- Read `report.md`
- Read `buggy/linefmt.py`
- Ran `python -c "..."` (throwaway, not saved) from inside `buggy/` to
  hand-verify the toggle trace on several candidate inputs, including
  the final chosen reproduction line and a "control" line without an
  embedded quoted phrase
- Wrote `candidate_test.py` in the working directory
- Ran `cp candidate_test.py buggy/candidate_test.py`
- Ran `python -m pytest candidate_test.py -v` from inside `buggy/`
  (captured to a temp file, then printed and deleted)
- Ran `rm -f buggy/candidate_test.py`, `rm -rf buggy/__pycache__
  buggy/.pytest_cache` to restore `buggy/` to its original state
- Ran `ls -la buggy/` to confirm only `linefmt.py` (474 bytes) remains
