import pytest

from inventory import adjust_stock


def test_adjustment_does_not_drop_stock_below_zero():
    """Reproduces the reported bug: an adjustment that removes more units
    than are on hand lets the stock count go negative (report.md: a SKU
    showed up as -3 units in stock; 'Stock counts should never go
    negative').
    """
    stock = {"SKU-1": 2}

    result = adjust_stock(stock, "SKU-1", -5)

    # Sanity check on the arithmetic the buggy function performs.
    assert result == -3

    # This is the actual bug: stock should never go negative.
    assert result >= 0
    assert stock["SKU-1"] >= 0
