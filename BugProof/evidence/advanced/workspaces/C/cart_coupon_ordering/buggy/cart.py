class ShoppingCart:
    def __init__(self):
        self.items = []
        self.total = 0

    def add_item(self, price):
        self.items.append(price)
        self.total += price

    def apply_coupon(self, percent_off):
        self.total = self.total - (self.total * percent_off / 100)

    def checkout(self):
        return round(self.total, 2)
