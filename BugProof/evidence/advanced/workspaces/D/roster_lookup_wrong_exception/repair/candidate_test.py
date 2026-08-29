import pytest

from roster import find_member


def test_find_member_existing_id_works():
    """report.md: 'looking up ids that do exist works fine'."""
    members = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    found = find_member(members, 1)
    assert found == {"id": 1, "name": "Alice"}


def test_find_member_missing_id_does_not_raise_indexerror():
    """report.md: looking up a missing id currently "throws an unhandled
    error" instead of giving a normal '"member not found"' response, and the
    observed error is 'IndexError: list index out of range'.

    We cannot ground exactly what the corrected behavior should look like
    (report.md never says whether it should return None, raise KeyError,
    raise LookupError, etc.) so this test only asserts the one thing
    report.md actually establishes: the lookup must not blow up with a raw,
    unhandled IndexError. Any other outcome (a return value, or a different,
    handleable exception) is acceptable.
    """
    members = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    try:
        find_member(members, 999)
    except IndexError:
        pytest.fail(
            "find_member raised an unhandled IndexError for a missing id; "
            "report.md says this should be a normal 'member not found' "
            "response instead"
        )
    except Exception:
        # Any other exception (e.g. KeyError/LookupError) is an acceptable,
        # handleable "not found" signal per report.md.
        pass
