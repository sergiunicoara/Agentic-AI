from handles import normalize_handle


def test_multiple_spaces_collapse_to_a_single_underscore():
    result = normalize_handle("Jane   Doe")

    assert result == "jane_doe"
