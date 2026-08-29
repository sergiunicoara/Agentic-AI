# Trajectory

Read report.md: two different users' shopping carts are sharing state. User A
called an add-to-cart function without passing a cart, then user B called the
same function (also without passing a cart), and user B's cart already
contained user A's "apple" item.

Read buggy/session_cache.py:

```python
def add_item(item, cart=[]):
    """Add an item to a shopping cart and return the updated cart."""
    cart.append(item)
    return cart
```

This is the classic Python mutable-default-argument pitfall: `cart=[]` is
evaluated once at function definition time, and every call that omits the
`cart` argument reuses and mutates that same list object. Once user A calls
`add_item("apple")`, that list contains "apple" forever after, and any
subsequent caller (user B) who also omits `cart` gets the same shared list
instead of a fresh empty cart -- exactly the "stale cache between users"
symptom in the report.

Wrote candidate_test.py (in the working directory, importing `from
session_cache import add_item`) with a test that calls `add_item("apple")`
for a simulated user A, then calls `add_item("banana")` for a simulated user
B, and asserts user B's resulting cart is `["banana"]` only (not containing
"apple").

Verified per instructions: copied candidate_test.py into buggy/, ran `pytest
candidate_test.py -v` from there. The test failed as expected, with
`cart_b == ['apple', 'banana']` instead of `['banana']`, confirming the test
reproduces the reported defect. Removed the temporary copy and any generated
`__pycache__`/`.pytest_cache` artifacts from buggy/ afterward, leaving
buggy/session_cache.py byte-for-byte unchanged.
