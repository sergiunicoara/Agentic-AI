from session_cache import add_item


def test_new_caller_without_explicit_cart_starts_empty():
    add_item("apple")

    second_cart = add_item("banana")

    assert second_cart == ["banana"]
