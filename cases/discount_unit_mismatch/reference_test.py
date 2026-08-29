from pricing import apply_discount


def test_twenty_percent_off_reduces_price_by_a_fifth():
    result = apply_discount(100, 20)

    assert result == 80
