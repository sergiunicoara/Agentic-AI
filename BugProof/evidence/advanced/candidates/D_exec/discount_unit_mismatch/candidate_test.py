from pricing import apply_discount


def test_apply_discount_20_percent_off_100_dollar_item():
    """
    Reproduces the bug from report.md: a $100 item with a 20%-off code
    should come out to a total of $80, but instead comes out to almost
    negative $1900.

    apply_discount treats `percent_off` as a fraction (e.g. 0.20 for
    20%), but the checkout code path is evidently calling it with the
    whole-number percent (20) instead, causing:
        price - (price * percent_off) = 100 - (100 * 20) = -1900
    instead of the expected:
        100 - (100 * 0.20) = 80
    """
    total = apply_discount(100, 20)
    assert total == 80
