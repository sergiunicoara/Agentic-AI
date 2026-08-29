from roster import find_member


def test_find_member_returns_existing_member():
    members = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    result = find_member(members, 2)

    assert result == {"id": 2, "name": "Bob"}


def test_find_member_missing_id_does_not_raise_indexerror():
    """
    Regression test for the reported bug: looking up an id that is not
    present in the roster must not blow up with an unhandled IndexError.
    Callers rely on a normal "not found" result (e.g. None) so they can
    respond gracefully instead of the request failing hard.
    """
    members = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    result = find_member(members, 999)

    assert result is None


def test_find_member_missing_id_on_empty_roster():
    result = find_member([], 42)

    assert result is None
