from linefmt import parse_line


def test_embedded_quoted_phrase_keeps_quote_marks_and_field_count():
    """A double-quote that appears in the middle of a field (not at the
    start of the field, right after a delimiter) is not a CSV "opening
    quote" -- it is just a literal character typed by the user, e.g. a
    product description like: Best "Value" Pack.

    Because it isn't a real quoted CSV field, the quote marks should be
    kept in the output value, and the delimiters elsewhere on the line
    should split fields exactly as normal.
    """
    line = '1,Best "Value" Pack of 3,12.50,In Stock'

    fields = parse_line(line)

    assert fields == ["1", 'Best "Value" Pack of 3', "12.50", "In Stock"]


def test_embedded_quoted_phrase_with_comma_does_not_swallow_next_field():
    """Reproduces the reported catalog-import bug: a description field
    contains a quoted phrase (quotes not at the start of the field), and
    that phrase happens to contain a comma, e.g.:

        Chair with "modern, sleek" design

    Since the quotes here are just literal punctuation (they don't open a
    real CSV-quoted field), the comma inside them is a genuine field
    separator and must still split the line into separate fields, with
    the quote marks preserved verbatim in the output.

    The buggy parser instead treats the bare quote character as toggling
    a global "in quotes" state for the rest of the line. That both
    strips the quote marks from the value AND causes the comma right
    after the quoted phrase to be swallowed instead of splitting a new
    field, shifting every field boundary that follows.
    """
    line = '1,Chair with "modern, sleek" design,29.99,In Stock'

    fields = parse_line(line)

    # Quote marks must survive, and the comma inside them is a real
    # delimiter, so the line splits into five fields, not four.
    assert fields == [
        "1",
        'Chair with "modern',
        ' sleek" design',
        "29.99",
        "In Stock",
    ]
    assert len(fields) == 5


def test_normal_unquoted_row_is_unaffected():
    """Sanity check matching the report's "most rows import fine" note --
    a row with no quote characters at all must be unaffected."""
    line = "2,Plain Desk Lamp,9.99,In Stock"

    fields = parse_line(line)

    assert fields == ["2", "Plain Desk Lamp", "9.99", "In Stock"]
