def add_item(item, cart=None):
    """Add an item to a shopping cart and return the updated cart."""
    if cart is None:
        cart = []
    cart.append(item)
    return cart
