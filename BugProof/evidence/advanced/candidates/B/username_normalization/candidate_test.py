from handles import normalize_handle


def test_multiple_spaces_collapse_to_single_underscore():
    """Extra spaces between words should still yield a single-underscore handle.

    Per report.md: a display name typed with two spaces between words
    (e.g. "Jane  Doe") is producing handles like "jane___doe" (multiple
    underscores) instead of the usual single-underscore style "jane_doe".
    """
    assert normalize_handle("Jane  Doe") == "jane_doe"


def test_many_extra_spaces_still_collapse():
    assert normalize_handle("Jane     Doe") == "jane_doe"


def test_single_space_still_works():
    assert normalize_handle("Jane Doe") == "jane_doe"
