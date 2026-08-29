from handles import normalize_handle


def test_simple_name_becomes_lowercase_with_underscore():
    assert normalize_handle("Jane Doe") == "jane_doe"
