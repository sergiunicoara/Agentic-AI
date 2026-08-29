from session_cache import add_item


def test_add_item_with_explicit_cart():
    cart = ["existing"]

    result = add_item("new", cart)

    assert result == ["existing", "new"]
