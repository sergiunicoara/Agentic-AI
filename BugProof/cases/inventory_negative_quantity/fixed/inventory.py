def adjust_stock(stock, sku, delta):
    """Apply a stock adjustment (positive or negative) to a sku."""
    new_amount = stock.get(sku, 0) + delta
    if new_amount < 0:
        raise ValueError(f"adjustment would leave {sku!r} with negative stock: {new_amount}")
    stock[sku] = new_amount
    return stock[sku]
