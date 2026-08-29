def adjust_stock(stock, sku, delta):
    """Apply a stock adjustment (positive or negative) to a sku."""
    stock[sku] = stock.get(sku, 0) + delta
    return stock[sku]
