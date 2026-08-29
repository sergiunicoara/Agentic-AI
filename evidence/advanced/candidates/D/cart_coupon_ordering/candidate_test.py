"""Reproduces the bug from report.md:

  "adding an item, applying the coupon, then adding a second item -- the
  second item came out at full price, like the coupon only covered part
  of the cart."

ShoppingCart.apply_coupon (buggy/cart.py) computes a one-time discount off
whatever `self.total` happens to be at the moment it is called:

    self.total = self.total - (self.total * percent_off / 100)

It does not remember the coupon for later add_item() calls. So any item
added *after* apply_coupon() is added at full price, while items added
*before* it were discounted. The final total therefore depends on the
order of operations, even though a coupon is conceptually meant to apply
to the whole order.
"""

from cart import ShoppingCart


def test_coupon_applied_before_second_item_added_should_discount_whole_cart():
    cart = ShoppingCart()

    cart.add_item(50)          # item #1, added before the coupon
    cart.apply_coupon(20)      # 20% off coupon
    cart.add_item(50)          # item #2, added after the coupon

    actual = cart.checkout()

    # A coupon that truly applies to the whole order should discount the
    # combined value of both items: (50 + 50) - (50 + 50) * 20 / 100 = 80.
    expected = 80

    assert actual == expected, (
        f"expected the coupon to discount the whole cart to {expected}, "
        f"but got {actual}: the second item was added after apply_coupon() "
        "and came out at full price instead of being discounted."
    )


def test_coupon_applied_after_all_items_added_matches_same_total():
    # Sanity check reflecting the second customer's report: adding
    # everything to the cart before entering the coupon code "worked fine"
    # -- i.e. produces the fully-discounted total, unlike the order above.
    cart = ShoppingCart()

    cart.add_item(50)
    cart.add_item(50)
    cart.apply_coupon(20)

    actual = cart.checkout()
    expected = 80

    assert actual == expected
