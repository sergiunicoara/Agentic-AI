"""
Reproduces the bug described in report.md:

    A coupon applied before all items are added only discounts the items
    that were already in the cart at the time apply_coupon() was called.
    Any item added *after* the coupon is applied comes out at full price,
    while the same items in the opposite order (add everything, then apply
    the coupon) get the discount applied correctly to the whole cart.

A customer should get the same final total for the same cart contents and
the same coupon, regardless of whether they added an item before or after
entering the coupon code.
"""

from cart import ShoppingCart


def test_coupon_applies_regardless_of_order_items_added():
    # Customer A: applies the coupon in the middle of shopping.
    cart_apply_early = ShoppingCart()
    cart_apply_early.add_item(100)
    cart_apply_early.apply_coupon(10)  # 10% off
    cart_apply_early.add_item(100)  # added after the coupon was applied

    # Customer B: adds everything first, then applies the same coupon.
    cart_apply_late = ShoppingCart()
    cart_apply_late.add_item(100)
    cart_apply_late.add_item(100)
    cart_apply_late.apply_coupon(10)  # 10% off

    # Both carts have identical contents ($100 + $100) and the same 10%
    # coupon, so both customers should see the same, fully-discounted total.
    expected_total = 180.0  # (100 + 100) * 0.90

    assert cart_apply_late.checkout() == expected_total

    # This is the assertion that captures the reported bug: applying the
    # coupon before the second item is added should not leave that second
    # item at full price.
    assert cart_apply_early.checkout() == expected_total
