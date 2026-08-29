Two different test users are seeing each other's cart items. I added "apple" for user A
with no cart passed in, then later called the same add-to-cart function for user B (also
no cart passed in), and user B's cart already had "apple" in it before they'd added
anything. Feels like something is shared between calls that shouldn't be.
