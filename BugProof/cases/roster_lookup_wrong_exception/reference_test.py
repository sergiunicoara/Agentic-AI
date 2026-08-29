import pytest

from roster import find_member


def test_lookup_of_missing_member_raises_a_lookup_error():
    members = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]

    with pytest.raises(KeyError):
        find_member(members, member_id=99)
