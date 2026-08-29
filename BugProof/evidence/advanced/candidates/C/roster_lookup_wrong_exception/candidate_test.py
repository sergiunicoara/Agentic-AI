import pytest

from roster import find_member


def test_find_member_missing_id_raises_indexerror_not_handled():
    """report.md: looking up an id that doesn't exist in the roster throws an
    unhandled IndexError ('list index out of range') instead of some kind of
    normal 'member not found' response (e.g. None or a KeyError/LookupError
    the caller could handle). Looking up an id that does exist works fine.
    """
    members = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    # Existing id works fine, as report.md says.
    found = find_member(members, 1)
    assert found == {"id": 1, "name": "Alice"}

    # Missing id currently blows up with an unhandled IndexError instead of
    # returning/raising something callers can treat as "member not found".
    with pytest.raises(IndexError):
        find_member(members, 999)
