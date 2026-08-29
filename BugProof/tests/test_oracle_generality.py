"""Regression coverage for the cart_coupon_ordering oracle, corrected twice
in Phase 2 for the same underlying problem: overfitting to how a
particular reference test happened to be written, not the reported defect
class.

Round 1: message_pattern was the literal string "95" -- the one numeric
value the reference's specific $50+$50 @ 10% example produces on buggy/.
A baseline-generated candidate reproduced the identical defect with
$100+$100 @ 10% (buggy=190, expected=180), independently passed on
fixed/, and was wrongly rejected as WRONG_SYMPTOM. Corrected to
"checkout\\(\\)", matching the failure's traceback referencing the
checkout() call.

Round 2: "checkout\\(\\)" was still expression-dependent. A test written
as `actual = cart.checkout(); assert actual == expected` reproduces the
identical defect, but pytest's assertion rewriting only decomposes the
assert *expression* itself -- since `checkout()` is called on the line
above and assigned to a plain variable, the failure text is just
"assert 89.5 == 85" with no "checkout()" substring anywhere. Proven here,
then corrected: cases/cart_coupon_ordering/buggy/conftest.py now observes
the actual call *sequence* (add_item before and after apply_coupon, then
checkout -- the bug report's own description) via pass-through method
wrappers, and prints one fixed marker string to stdout only when that
sequence is genuinely present. message_pattern now matches that marker.
This still uses the ordinary generic regex-over-stdout path in
verdict.py -- unchanged, no case-specific branch was added there -- the
new evidence is behavioral, not the matching mechanism.

Five scenarios prove the fix is both general and still discriminating:
the reference, a frozen real baseline candidate, two structurally
different valid reproductions (direct-assert and assigned-variable, each
with its own distinct numbers), and one deliberately unrelated failing
test that must still be rejected.
"""

from pathlib import Path

from bugproof.verdict import evaluate

REPO_ROOT = Path(__file__).resolve().parent.parent
CASE_DIR = REPO_ROOT / "cases" / "cart_coupon_ordering"

# $50 + $50 @ 10%: buggy checkout() = 95.0, expected = 90
REFERENCE_NUMBERS = CASE_DIR / "reference_test.py"

# The actual frozen Phase 2 baseline candidate, unedited.
# $100 + $100 @ 10%: buggy checkout() = 190.0, expected = 180.
FROZEN_BASELINE_CANDIDATE = (
    REPO_ROOT / "evidence" / "baseline" / "candidates" / "cart_coupon_ordering" / "candidate_test.py"
)

# $60 + $60 @ 20%: buggy checkout() = 108.0, expected = 96 -- direct-assert
# style (`assert cart.checkout() == 96`), distinct numbers from every
# other scenario in this file.
DIRECT_ASSERT_ALTERNATE_SOURCE = """\
from cart import ShoppingCart


def test_coupon_applies_to_items_added_after_it_too_alternate_numbers():
    cart = ShoppingCart()
    cart.add_item(60)
    cart.apply_coupon(20)
    cart.add_item(60)

    assert cart.checkout() == 96
"""

# $70 + $30 @ 15%: buggy checkout() = 89.5, expected = 85 -- assigned-
# variable style: checkout() is called on its own line, never appearing
# textually inside the assert statement. This is exactly the shape that
# defeated the "checkout\\(\\)" pattern.
ASSIGNED_VARIABLE_ALTERNATE_SOURCE = """\
from cart import ShoppingCart


def test_coupon_still_applies_when_assigned_to_variable():
    cart = ShoppingCart()
    cart.add_item(70)
    cart.apply_coupon(15)
    cart.add_item(30)

    actual = cart.checkout()
    expected = 85

    assert actual == expected
"""

# Deliberately unrelated: two items, no coupon at all, an arbitrary wrong
# expectation. Fails on buggy/ for a completely different reason and must
# not match the coupon-ordering symptom.
UNRELATED_FAILING_TEST_SOURCE = """\
from cart import ShoppingCart


def test_two_items_sum_to_an_unrelated_wrong_total():
    cart = ShoppingCart()
    cart.add_item(10)
    cart.add_item(20)

    assert cart.checkout() == 999
"""


def test_1_reference_numbers_verify_valid():
    result = evaluate(CASE_DIR, REFERENCE_NUMBERS)
    assert result.status == "VALID", (result.reason, result.detail)


def test_2_frozen_baseline_candidate_verifies_valid():
    assert FROZEN_BASELINE_CANDIDATE.exists(), "frozen Phase 2 candidate is missing"

    result = evaluate(CASE_DIR, FROZEN_BASELINE_CANDIDATE)

    assert result.status == "VALID", (result.reason, result.detail)


def test_3_direct_assert_alternate_reproduction_verifies_valid(tmp_path):
    candidate = tmp_path / "direct_assert_candidate_test.py"
    candidate.write_text(DIRECT_ASSERT_ALTERNATE_SOURCE)

    result = evaluate(CASE_DIR, candidate)

    assert result.status == "VALID", (result.reason, result.detail)


def test_4_assigned_variable_alternate_reproduction_verifies_valid(tmp_path):
    candidate = tmp_path / "assigned_variable_candidate_test.py"
    candidate.write_text(ASSIGNED_VARIABLE_ALTERNATE_SOURCE)

    result = evaluate(CASE_DIR, candidate)

    assert result.status == "VALID", (result.reason, result.detail)


def test_5_unrelated_failing_test_is_rejected_as_wrong_symptom(tmp_path):
    candidate = tmp_path / "unrelated_candidate_test.py"
    candidate.write_text(UNRELATED_FAILING_TEST_SOURCE)

    result = evaluate(CASE_DIR, candidate)

    assert result.status == "REJECTED"
    assert result.reason == "WRONG_SYMPTOM"
