class ShoppingCart:
    def __init__(self):
        self.items = []
        self.discount_percent = 0

    def add_item(self, price):
        self.items.append(price)

    def apply_coupon(self, percent_off):
        self.discount_percent = percent_off

    def checkout(self):
        subtotal = sum(self.items)
        return round(subtotal - (subtotal * self.discount_percent / 100), 2)
