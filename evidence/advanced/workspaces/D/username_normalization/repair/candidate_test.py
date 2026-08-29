from handles import normalize_handle


def test_double_space_produces_single_underscore():
    """report.md: users are getting handles like 'jane___doe' "instead of
    the usual single-underscore style everyone else has" when a display
    name has extra spaces between words (e.g. 'Jane  Doe' with two spaces).

    normalize_handle uses raw.strip().lower().replace(" ", "_"), which
    replaces every individual space character with its own underscore, so
    multiple consecutive spaces become multiple consecutive underscores
    instead of collapsing into one.

    report.md never quotes the exact fixed string "jane_doe" verbatim, so
    we do not assert that exact literal here (that assertion was flagged
    as ungrounded). What report.md DOES support is the qualitative claim
    that correct handles use "the usual single-underscore style" -- i.e.
    no run of two-or-more underscores. That is directly checkable without
    inventing an exact value.
    """
    result = normalize_handle("Jane  Doe")
    assert "__" not in result


def test_triple_space_produces_single_underscore():
    """Same bug, three spaces instead of two. report.md's own quoted
    example of the broken output is "jane___doe" (triple underscore),
    which is exactly what normalize_handle("Jane   Doe") produces on the
    buggy implementation (three space chars each individually replaced by
    "_"). We assert the desired/fixed behavior -- no double-or-more
    underscore run -- rather than pinning an exact "correct" string that
    is never quoted in report.md.
    """
    result = normalize_handle("Jane   Doe")
    assert "__" not in result
