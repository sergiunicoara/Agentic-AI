# Trajectory

**Read:** `report.md` (a product-catalog import mangled a description field:
embedded quote marks disappeared, and the field boundary right after that
point looked shifted; most rows import fine) and `buggy/linefmt.py`, a
17-line `parse_line(line, delimiter=",")` function.

**What the code does:** it scans the line character by character and
toggles a single `in_quotes` boolean every time it sees a `"`, anywhere in
the line. While `in_quotes` is true, the delimiter is treated as a literal
character instead of a field separator, and `"` characters are never
appended to the current field (they're consumed purely as toggles). There
is no concept of "a quote only starts a field when it appears right after a
delimiter" (RFC4180 semantics) and no support for doubled `""` escaping.

**Conclusion about the bug:** any `"` appearing in the middle of a field
(e.g. a product description using quote marks around a word, like
`Best "Value" Pack`) is wrongly treated as if it opened/closed a real
quoted CSV field. This has two visible effects that match the report
exactly: (1) the quote characters are stripped from the value instead of
being preserved as literal text, and (2) if that embedded quoted phrase
happens to contain the delimiter (e.g. `Chair with "modern, sleek" design`),
the delimiter inside it is incorrectly swallowed instead of splitting a new
field, merging fields that should stay separate and shifting every field
boundary after that point. I verified expected behavior against Python's
own `csv` module for a case without commas inside the quotes to confirm the
"quotes should be preserved when not at a field boundary" expectation, then
confirmed by direct reasoning about RFC4180 semantics for the comma-inside
case.

**Test file:** `candidate_test.py` (repo root, imports `from linefmt import
parse_line`) contains three tests:
- `test_embedded_quoted_phrase_keeps_quote_marks_and_field_count` — a
  description with a quoted word and no internal delimiter; asserts quotes
  are preserved.
- `test_embedded_quoted_phrase_with_comma_does_not_swallow_next_field` — the
  core reproduction: a description with a quoted phrase containing a comma;
  asserts quotes are preserved AND the line splits into 5 fields (not 4),
  directly reproducing the "field boundary shifted" symptom.
- `test_normal_unquoted_row_is_unaffected` — sanity check matching the
  report's "most rows import fine" note.

**Verification run:** per the one-shot check allowance, I copied
`candidate_test.py` into `buggy/`, ran `pytest -v` from there, and observed
2 failed / 1 passed: both quote-related tests failed against the current
buggy code exactly as expected (quote marks stripped; 4 fields instead of
5), while the plain-row sanity test passed. I then deleted the temporary
copy (and the `__pycache__` directory pytest created) from `buggy/`,
confirming `buggy/` is back to containing only the original `linefmt.py`,
unmodified.
