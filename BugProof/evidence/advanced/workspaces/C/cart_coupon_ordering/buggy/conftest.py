"""Deterministic, evidence-based symptom marker for this case's oracle.

The generic oracle mechanism (regex over a run's stdout/stderr/failure
text, in verdict.py) proved unable to express this case's symptom without
overfitting: a literal number ("95") overfits to one reference test's
arithmetic; a text pattern tied to the assert expression's shape
("checkout\\(\\)") overfits to whether the call happens to appear inside
the assert statement itself -- `actual = cart.checkout(); assert actual
== expected` produces a failure with no "checkout()" substring anywhere,
even though it reproduces the identical defect.

This file replaces both with a check of what actually happened, not how
it was written down. It wraps ShoppingCart.add_item/apply_coupon/checkout
to observe the call *sequence* (pass-through wrappers only -- behavior is
never altered), and prints one fixed marker string to stdout if and only
if the sequence exhibits the structural precondition for the reported
defect: at least one add_item() both before and after an apply_coupon()
call, followed by a checkout() call. That precondition is what the bug
report actually describes ("added an item, applied the coupon, added
another item") -- it does not depend on which numbers, variable names, or
assert phrasing a given test uses.

oracle.yaml's message_pattern matches this fixed marker string. This does
not touch verdict.py or sandbox.py: the marker is picked up through the
same generic regex-over-stdout path every other case uses, via pytest's
ordinary conftest.py auto-discovery -- nothing here is a new mechanism at
the evaluator level, only new evidence at the case level. It is not
copied into fixed/, so conditions 4 and 5 (which run against fixed/) are
completely unaffected by it.
"""

import cart

_events: list[str] = []

_original_add_item = cart.ShoppingCart.add_item
_original_apply_coupon = cart.ShoppingCart.apply_coupon
_original_checkout = cart.ShoppingCart.checkout


def _tracked_add_item(self, price):
    _events.append("add_item")
    return _original_add_item(self, price)


def _tracked_apply_coupon(self, percent_off):
    _events.append("apply_coupon")
    return _original_apply_coupon(self, percent_off)


def _tracked_checkout(self):
    _events.append("checkout")
    return _original_checkout(self)


cart.ShoppingCart.add_item = _tracked_add_item
cart.ShoppingCart.apply_coupon = _tracked_apply_coupon
cart.ShoppingCart.checkout = _tracked_checkout


def pytest_sessionfinish(session, exitstatus):
    if "apply_coupon" not in _events:
        return

    coupon_index = _events.index("apply_coupon")
    before = _events[:coupon_index]
    after = _events[coupon_index + 1 :]

    add_before = "add_item" in before
    add_after = "add_item" in after
    checkout_after_the_later_add = (
        add_after and "checkout" in after[after.index("add_item") + 1 :]
    )

    if add_before and add_after and checkout_after_the_later_add:
        print("BUGPROOF_ORDER_DEPENDENT_COUPON_PATTERN_OBSERVED")
