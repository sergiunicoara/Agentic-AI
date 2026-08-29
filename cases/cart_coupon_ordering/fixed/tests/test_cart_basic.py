from cart import ShoppingCart


def test_checkout_with_no_coupon_returns_the_subtotal():
    cart = ShoppingCart()
    cart.add_item(20)
    cart.add_item(30)

    assert cart.checkout() == 50
