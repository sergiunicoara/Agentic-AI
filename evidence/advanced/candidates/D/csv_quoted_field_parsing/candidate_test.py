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
    # Build the line out of three explicit field values, joined by the
    # delimiter, so the CORRECT number of output fields is directly
    # re-computable from these setup values instead of being asserted
    # as a bare, hand-counted magic number.
    id_field = "101"
    description_field = 'He said "ok, sure" today'
    price_field = "29.99"

    setup_fields = [id_field, description_field, price_field]
    line = f'{id_field},"{description_field}",{price_field}'

    fields = parse_line(line, ",")

    # parse_line's own docstring states its contract: "Split a single
    # delimited line into fields, respecting double-quoted fields."
    # Under that contract, description_field -- itself wrapped in
    # double quotes when embedded in `line` above -- must come back as
    # a single field, regardless of the delimiter character it
    # contains or the embedded quoted phrase ("ok, sure") inside it.
    # So the number of output fields must equal the number of setup
    # fields that were joined to build the line.
    expected_field_count = len(setup_fields)
    assert len(fields) == expected_field_count

    # The whole description -- including the comma that lives inside
    # the embedded quoted phrase -- must stay together in a single
    # field, not be broken into two separate fields.
    assert "He said" in fields[1]
    assert "sure" in fields[1]
    assert "today" in fields[1]
