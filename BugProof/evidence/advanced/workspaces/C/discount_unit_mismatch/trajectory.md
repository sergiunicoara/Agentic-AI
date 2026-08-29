# Trajectory

## What I read

- `report.md`: describes that checkout totals are wrong whenever a discount
  code is applied. Specific example: a $100 item with a 20%-off code
  produces a total of "almost negative $1900" instead of the expected $80.
  Checkout without a discount code works fine. Bug has existed since the
  discount-codes feature shipped.

- `buggy/pricing.py`: the only file in `buggy/`. Contains a single function:

  ```python
  def apply_discount(price, percent_off):
      """Return the price after applying a percentage discount."""
      return price - (price * percent_off)
  ```

## What I concluded

`apply_discount`'s formula (`price - price * percent_off`) is only correct
if `percent_off` is passed in as a fraction (e.g. `0.20` for 20% off). The
report's numbers are a direct fingerprint of a unit mismatch: if the caller
instead passes the whole-number percent (`20` for "20%"), the function
computes `100 - (100 * 20) = -1900`, which matches the report's "almost
negative $1900" exactly. With the correct fractional unit (`0.20`), the
same call would produce `100 - (100 * 0.20) = 80`, matching the report's
expected total. Since `pricing.py` is the only source file present, and its
docstring gives no indication of which unit is expected, the reproducible
bug is that calling `apply_discount` with a whole-number percent (as a
"20%-off code" naturally suggests) silently produces a wildly wrong,
negative total instead of either raising an error or returning the correct
discounted price.

## Test written

`candidate_test.py` (in the working directory, sibling of `report.md` and
`buggy/`) calls `apply_discount(100, 20)` and asserts the result equals
`80`, mirroring the report's exact scenario (a $100 item, a 20%-off code,
expected total $80).

## What happened when I ran it

Per the required one-time check: I copied `candidate_test.py` into
`buggy/`, ran `python -m pytest candidate_test.py -v` from inside `buggy/`,
observed the result, then deleted the copy (and the `__pycache__`/
`.pytest_cache` directories the run created) from `buggy/`.

Observed output:

```
candidate_test.py::test_apply_discount_20_percent_off_100_dollar_item FAILED

    total = apply_discount(100, 20)
>   assert total == 80
E   assert -1900 == 80

1 failed in 1.17s
```

The test fails with `assert -1900 == 80` — i.e., calling
`apply_discount(100, 20)` actually returns `-1900`, exactly matching the
report's "almost negative $1900" for a $100 item with a 20%-off code,
instead of the expected $80. This reproduces the reported bug.

After the run, `buggy/` was restored to contain only `pricing.py`
(the temporary test copy and pytest cache artifacts were removed), leaving
it byte-for-byte as it started.

## Files read / commands run:

- Read `report.md`
- Read `buggy/pricing.py`
- Wrote `candidate_test.py` in the working directory
- Ran (bash): `cp candidate_test.py buggy/candidate_test.py`
- Ran (bash): `cd buggy && python -m pytest candidate_test.py -v`
- Ran (bash): `rm buggy/candidate_test.py`
- Ran (bash): `rm -rf buggy/__pycache__` and `rm -rf .pytest_cache`
- Ran (bash): `find buggy -type f` (to confirm `buggy/` contains only `pricing.py` afterward)
