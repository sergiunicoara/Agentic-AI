from session_cache import add_item


def test_cart_not_shared_between_users_with_no_cart_passed_in():
    """Reproduces report.md: user A adds "apple" with no cart passed in,
    then user B (also no cart passed in) should start with an empty
    cart, not see user A's "apple" already present.
    """
    cart_a = add_item("apple")
    assert cart_a == ["apple"]

    # Simulate a new user B making the same call with no cart argument.
    cart_b = add_item("banana")

    # Bug: because `cart=[]` is a mutable default argument evaluated once
    # at function definition time, cart_b is the *same* list object as
    # cart_a, so user B's cart already contains "apple" before they added
    # anything themselves.
    assert cart_b == ["banana"]
