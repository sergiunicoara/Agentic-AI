# Trajectory

Read `report.md`: customers say a coupon sometimes only partially discounts
the order. One customer added an item, applied the coupon, then added a
second item, and the second item came out at full price. Another customer
who added all items before entering the coupon got the full discount.

Read `buggy/cart.py`, the only source file. `ShoppingCart.apply_coupon`
computes `self.total = self.total - (self.total * percent_off / 100)` --
it discounts whatever `self.total` happens to be *at the moment it is
called*, and does not remember the coupon percentage. `add_item` simply
does `self.total += price` with no awareness that a coupon was ever
applied. So any item added after `apply_coupon()` is added at full,
undiscounted price, while items added before it get the discount. This
exactly matches the report: order of operations changes the outcome, and
"add everything first, then apply the coupon" is the only order that
produces the fully-discounted total.

Wrote `candidate_test.py` (in the working directory, importing `from cart
import ShoppingCart` per the stated execution setup) with a test that
builds two carts with identical contents ($100 + $100) and the same 10%
coupon, differing only in whether the coupon is applied before or after
the second item is added. Both should checkout at $180.00 (10% off the
full $200 cart) per the reasonable customer expectation from the report.

Verified per the one-shot check procedure: copied `candidate_test.py` into
`buggy/`, ran `pytest` from there, and it failed as expected --
`cart_apply_late.checkout()` correctly returned 180.0, but
`cart_apply_early.checkout()` returned 190.0 (the second $100 item was
never discounted), triggering `assert 190.0 == 180.0`. Removed the
temporary copy and any `__pycache__`/`.pytest_cache` directories created
by the run afterward; `buggy/cart.py` was never modified and `buggy/` now
contains only the original `cart.py`.
