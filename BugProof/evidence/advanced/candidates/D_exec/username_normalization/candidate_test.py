from handles import normalize_handle


def test_double_space_produces_single_underscore():
    """report.md: 'jane___doe' instead of the usual single-underscore style
    happens when 'Jane  Doe' has two spaces instead of one.

    normalize_handle uses raw.strip().lower().replace(" ", "_"), which
    replaces every individual space character with an underscore, so two
    consecutive spaces become two consecutive underscores instead of
    collapsing into one. The expected/desired behavior is a single
    underscore between words regardless of how many spaces separated them.
    """
    result = normalize_handle("Jane  Doe")
    assert result == "jane_doe"


def test_triple_space_produces_single_underscore():
    result = normalize_handle("Jane   Doe")
    assert result == "jane_doe"
