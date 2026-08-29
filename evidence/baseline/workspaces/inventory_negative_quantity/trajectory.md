# Trajectory

**Read:** `report.md` (a SKU showed -3 units in stock after an adjustment; stock
should never go negative) and `buggy/inventory.py`, a 4-line module exposing
`adjust_stock(stock, sku, delta)` which does `stock[sku] = stock.get(sku, 0) +
delta` and returns the new value — no bounds checking at all.

**Conclusion:** The function blindly applies any delta, including a negative
delta larger than the current on-hand quantity, producing a negative stock
value. This matches the report exactly: nothing in the adjustment logic
prevents stock from going below zero. The natural expected behavior is that
an adjustment which would remove more units than are on hand is rejected
(raising an error) and leaves the recorded stock unchanged, while an
adjustment that exactly depletes stock to zero is still valid.

**Test:** Wrote `candidate_test.py` with two cases: (1) applying a delta of
-5 to a stock of 2 must raise `ValueError` and must not mutate the stored
stock value, and (2) applying a delta that exactly zeroes out stock (5 units,
delta -5) is allowed and returns 0.

**Verification run:** Temporarily copied `candidate_test.py` into `buggy/`
and ran `pytest` from there. Result: `test_adjustment_cannot_take_stock_negative`
FAILED with `Failed: DID NOT RAISE <class 'ValueError'>` (current code lets
stock go negative, exactly the reported bug), while
`test_adjustment_exactly_depleting_stock_is_allowed` PASSED. Removed the
temporary copy plus the `__pycache__`/`.pytest_cache` artifacts pytest
created, so `buggy/` is back to containing only the original `inventory.py`,
unmodified.
