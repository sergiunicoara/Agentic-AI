from session_cache import add_item


def test_new_user_cart_does_not_contain_previous_users_items():
    """Regression test for stale-cache-between-users bug.

    Two different users each call add_item without passing an explicit
    cart. Per report.md, user A adds "apple" (no cart passed in), then
    later user B adds to their own cart (also no cart passed in). User
    B's cart should start empty and only contain what user B added --
    it must not already contain "apple" from user A.
    """
    cart_a = add_item("apple")
    assert cart_a == ["apple"]

    # Simulate a separate user's request later on, also with no cart
    # explicitly supplied.
    cart_b = add_item("banana")

    assert cart_b == ["banana"], (
        f"user B's cart leaked items from a previous user's session: {cart_b!r}"
    )
