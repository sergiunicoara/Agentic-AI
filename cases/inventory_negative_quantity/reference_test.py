import pytest

from inventory import adjust_stock


def test_adjustment_that_would_go_negative_is_rejected():
    stock = {"widget": 2}

    with pytest.raises(ValueError):
        adjust_stock(stock, "widget", -5)
