from roster import find_member


def test_lookup_of_existing_member_returns_the_record():
    members = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]

    result = find_member(members, member_id=2)

    assert result == {"id": 2, "name": "Grace"}
