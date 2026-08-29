from pricing import apply_discount


def test_apply_discount_with_whole_number_percent():
    """A 20%-off code on a $100 item should total $80, per report.md.

    apply_discount is called with percent_off expressed as a whole number
    (20 meaning 20%), matching how discount codes are represented/reported
    in the checkout flow. The current implementation treats percent_off as
    if it were already a fraction (0.2), so it computes
    100 - (100 * 20) = -1900 instead of 80.
    """
    total = apply_discount(100, 20)
    assert total == 80


def test_apply_discount_ten_percent_off_fifty():
    """A second, independent case: 10% off $50 should be $45."""
    total = apply_discount(50, 10)
    assert total == 45
