def apply_discount(price, percent_off):
    """Return the price after applying a percentage discount (0-100)."""
    return price - (price * (percent_off / 100))
