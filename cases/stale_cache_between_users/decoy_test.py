from session_cache import add_itme


def test_new_caller_without_explicit_cart_starts_empty():
    add_itme("apple")

    second_cart = add_itme("banana")

    assert second_cart == ["banana"]
