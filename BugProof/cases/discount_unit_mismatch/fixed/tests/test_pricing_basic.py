from pricing import apply_discount


def test_zero_percent_off_returns_original_price():
    assert apply_discount(50, 0) == 50
