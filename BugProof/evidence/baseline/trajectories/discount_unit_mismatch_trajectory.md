# Trajectory

Read report.md: a $100 item with a "20%-off" code totals almost negative $1900
instead of $80; checkout with no discount code works fine.

Inspected buggy/pricing.py, the only source file present:

```python
def apply_discount(price, percent_off):
    """Return the price after applying a percentage discount."""
    return price - (price * percent_off)
```

Conclusion: this is a unit mismatch. The function treats `percent_off` as
already being a fraction (e.g. 0.2 for 20%), but discount codes are clearly
represented/passed as whole-number percentages (e.g. 20 for 20%). Calling
`apply_discount(100, 20)` computes `100 - (100 * 20) = -1900`, which matches
the report's "almost negative $1900" almost exactly. The expected result is
`100 - (100 * 0.20) = 80`. No-discount checkout is unaffected because that
code path presumably never calls this function (or calls it with 0), which
matches the report that undiscounted checkout works fine.

Wrote candidate_test.py with two cases: `apply_discount(100, 20) == 80` and
`apply_discount(50, 10) == 45`, both expressing percent_off as a whole
number as a user/discount-code would specify it.

Verification (one-time, per instructions): copied candidate_test.py into
buggy/, ran `pytest` from there. Both tests failed against the current code:
`assert -1900 == 80` and `assert -450 == 45` — the first mismatch reproduces
the exact number from the bug report. Removed the temporary copy and the
generated `__pycache__` directory afterward; buggy/ now contains only the
original pricing.py, unmodified.
