from session_cache import add_item


def test_cart_not_shared_between_users_with_no_cart_passed_in():
    """Reproduces report.md: user A adds "apple" with no cart passed in,
    then user B (also no cart passed in) should start with an empty
    cart, not see user A's "apple" already present.
    """
    cart_a = add_item("apple")

    # session_cache.py defines `def add_item(item, cart=[]):` -- the
    # default list starts empty (evaluated once at function-def time),
    # and this is the first call in the test, so after one append its
    # length is derived as 0 + 1 = 1.
    assert len(cart_a) == 1
    assert "apple" in cart_a

    # Simulate a new user B making the same call with no cart argument.
    cart_b = add_item("banana")

    # Per report.md: "user B's cart already had \"apple\" in it before
    # they'd added anything" describes the *bug*. Correct behavior is
    # the opposite -- user B's own call should only add "banana", so
    # "apple" should NOT be present, and the cart length should be its
    # own single append: 0 + 1 = 1.
    assert "apple" not in cart_b
    assert len(cart_b) == 1
