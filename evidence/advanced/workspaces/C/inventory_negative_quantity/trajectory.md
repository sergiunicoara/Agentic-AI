# Trajectory

## What I read

- `report.md`: describes a warehouse SKU that showed up as **-3 units in
  stock** in an export. States the invariant "Stock counts should never go
  negative" and says an adjustment let through a removal larger than what
  was actually on hand.
- `buggy/inventory.py`: a single 5-line module with one function,
  `adjust_stock(stock, sku, delta)`. It does
  `stock[sku] = stock.get(sku, 0) + delta` and returns the new value. There
  is no check anywhere that the resulting quantity is non-negative, and no
  check that `delta` (if negative) doesn't exceed the current on-hand
  quantity.

## What I concluded

The bug is exactly what it looks like: `adjust_stock` blindly applies any
delta, positive or negative, with no floor at zero and no validation
against current stock. Any caller that applies a negative adjustment
larger than the current quantity will drive the stock count negative,
matching the report's observed "-3 units in stock" (e.g. 2 units on hand,
a -5 adjustment, is not rejected or clamped, and yields -3).

## Test

`candidate_test.py` (in the working directory, sibling to `report.md` and
`buggy/`) sets up a SKU with 2 units on hand and applies a -5 adjustment
via `adjust_stock`. It asserts:
1. The arithmetic itself (`result == -3`), which matches the report's
   `-3 units in stock` figure — a sanity check that the scenario mirrors
   the report.
2. The actual invariant from the report, that stock should never go
   negative (`result >= 0` and `stock["SKU-1"] >= 0`).

## What happened when I ran it

Per the task instructions, I copied `candidate_test.py` into `buggy/`,
ran it there with pytest from `buggy/`, and observed:

- Test collected: 1 item (`test_adjustment_does_not_drop_stock_below_zero`)
- Result: **FAILED**
- Failure point: `assert result >= 0` → `AssertionError: assert -3 >= 0`
- The first assertion (`result == -3`) passed, confirming the buggy
  function does compute and return -3 exactly as the report describes,
  before failing on the "never negative" invariant check.

I then removed the temporary copy (`buggy/candidate_test.py`) and the
pytest cache directories created during the run (`buggy/.pytest_cache`,
`buggy/__pycache__`), and confirmed `buggy/` contains only the original
`inventory.py`, unchanged.

## Files read / commands run:

- Read `report.md`
- Read `buggy/inventory.py`
- Wrote `candidate_test.py` in the working directory
- `cp candidate_test.py buggy/candidate_test.py`
- `cd buggy && python -m pytest candidate_test.py -v` — observed 1 failed,
  `AssertionError: assert -3 >= 0`
- `rm -f buggy/candidate_test.py`
- `rm -rf buggy/.pytest_cache buggy/__pycache__`
- `find buggy -type f` and `cat buggy/inventory.py` — confirmed only
  `inventory.py` remains, unmodified
