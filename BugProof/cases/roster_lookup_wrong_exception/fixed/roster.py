def find_member(members, member_id):
    """Return the member record with the given id."""
    matches = [m for m in members if m["id"] == member_id]
    if not matches:
        raise KeyError(member_id)
    return matches[0]
