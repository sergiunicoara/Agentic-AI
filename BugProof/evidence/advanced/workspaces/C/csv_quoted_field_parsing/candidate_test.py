"""
Reproduces the CSV quoted-field parsing bug described in report.md:

    "the source text has a quoted phrase inside it, and after import
    the embedded quote marks are just gone from the value, and it
    looks like the field boundary shifted somehow right after that
    point too."

parse_line() in linefmt.py toggles an `in_quotes` flag on every literal
`"` character it sees, without any special handling for a quoted phrase
that is embedded *inside* an already-quoted field (e.g. a description
field that itself needs quoting because it contains the delimiter, and
additionally contains a quoted phrase such as `"ok, sure"`). Each quote
character of that embedded phrase flips `in_quotes` again, so a
delimiter that sits inside the embedded phrase is treated as being
"outside" quotes and incorrectly splits the field -- exactly the
"field boundary shifted" symptom -- while the quote characters
themselves are never copied into the output, matching "the embedded
quote marks are just gone".
"""

from linefmt import parse_line


def test_embedded_quoted_phrase_does_not_split_the_field():
    # A product-catalog-style row: id, a description field that must be
    # quoted (it contains the delimiter) and additionally contains an
    # embedded quoted phrase ("ok, sure"), then a price field.
    #
    # There are exactly two REAL (unquoted, field-separating) commas in
    # this line: the one right after "101" and the one right after the
    # closing quote of the description, before "29.99". Everything else
    # -- including the comma inside the embedded phrase "ok, sure" --
    # sits inside the description field's own double quotes.
    line = '101,"He said "ok, sure" today",29.99'

    fields = parse_line(line, ",")

    # Correct behavior: 2 real delimiters -> 3 fields. The bug causes
    # an extra, spurious split right after the embedded quoted phrase,
    # so the buggy code actually returns 4 fields here.
    assert len(fields) == 3

    # The whole description -- including the comma that lives inside
    # the embedded quoted phrase -- must stay together in a single
    # field, not be broken into two separate fields.
    assert "He said" in fields[1]
    assert "sure" in fields[1]
    assert "today" in fields[1]
