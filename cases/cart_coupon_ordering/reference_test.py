from cart import ShoppingCart


def test_coupon_applies_to_items_added_after_it_too():
    cart = ShoppingCart()
    cart.add_item(50)
    cart.apply_coupon(10)
    cart.add_item(50)

    assert cart.checkout() == 90
