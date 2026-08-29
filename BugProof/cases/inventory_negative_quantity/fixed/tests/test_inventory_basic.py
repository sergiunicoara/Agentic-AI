from inventory import adjust_stock


def test_positive_adjustment_increases_stock():
    stock = {"widget": 2}

    result = adjust_stock(stock, "widget", 3)

    assert result == 5
