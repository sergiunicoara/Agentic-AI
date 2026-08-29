import pytest

from inventory import adjust_stock


def test_adjustment_cannot_take_stock_negative():
    """Stock counts should never go negative.

    Removing more units than are on hand (e.g. a -3 delta against 2
    units on hand) is an invalid adjustment and must be rejected,
    leaving the recorded stock level untouched.
    """
    stock = {"WIDGET-1": 2}

    with pytest.raises(ValueError):
        adjust_stock(stock, "WIDGET-1", -5)

    # The rejected adjustment must not have mutated the stock level.
    assert stock["WIDGET-1"] == 2


def test_adjustment_exactly_depleting_stock_is_allowed():
    """Bringing stock exactly to zero is a valid adjustment."""
    stock = {"WIDGET-1": 5}

    result = adjust_stock(stock, "WIDGET-1", -5)

    assert result == 0
    assert stock["WIDGET-1"] == 0
