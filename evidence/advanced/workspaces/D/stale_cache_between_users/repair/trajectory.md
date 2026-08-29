# Trajectory

## What changed and why

The prior candidate asserted exact list equalities:

```python
assert cart_a == ["apple"]
...
assert cart_b == ["banana"]
```

The evidence gate flagged both as NOT GROUNDED: neither `["apple"]` nor
`["banana"]` appears verbatim in report.md or buggy/session_cache.py, and
list-valued equalities cannot be grounded via `KIND: derived` because the
gate's arithmetic evaluator only handles plain-number +,-,*,/.

Per the repair instructions, I replaced every exact-list-value equality
with narrower assertions that ARE groundable:

- `len(cart_a) == 1` and `len(cart_b) == 1` -- numeric, derived from the
  known starting point (`cart=[]` in session_cache.py, an empty default
  list) plus one `.append()` call per test user: 0 + 1 = 1. This is a
  plain-number arithmetic derivation, which the gate's evaluator can
  check.
- `"apple" in cart_a` -- qualitative, directly supported by the source
  (`cart.append(item)` appends the passed item; the item passed was
  "apple").
- `"apple" not in cart_b` -- qualitative, the direct logical negation of
  the bug report.md describes: `"user B's cart already had \"apple\" in
  it before they'd added anything"`. Correct behavior is that this is
  NOT the case; the buggy code violates it.

This also fixes the test's logic relative to the actual bug: the
mutable-default-argument bug makes `cart_b` end up as
`['apple', 'banana']` (shared list object with `cart_a`), not
`['banana']` as the original candidate implicitly assumed. The new
assertions target exactly the symptom in the report (leftover "apple"
in user B's cart) without pinning an exact list literal.

## What I observed

Ran the revised test once, copied into buggy/ as a temp file, executed
with pytest, then removed the temp file and the `__pycache__` directory
pytest created (to keep buggy/ byte-for-byte unchanged):

- Result: 1 failed, 0 passed.
- Failure was exactly at `assert "apple" not in cart_b`, with pytest
  reporting `AssertionError: assert 'apple' not in ['apple', 'banana']`.
- This confirms: (1) `cart_a` assertions (`len(cart_a) == 1`,
  `"apple" in cart_a`) passed -- first call behaves correctly; (2) the
  test fails specifically because user B's cart already contains
  "apple" before user B added anything, i.e. it reproduces the exact
  symptom in report.md caused by the `cart=[]` mutable default argument
  in buggy/session_cache.py.
- buggy/ directory confirmed unchanged after cleanup (only
  session_cache.py present, original mtime intact).

## Files read / commands run

- Read: report.md
- Read: buggy/session_cache.py
- Bash: `ls -la buggy/` (initial contents check)
- Bash: `cp candidate_test.py buggy/test_candidate_temp.py && cd buggy && python -m pytest test_candidate_temp.py -v > ../test_run_output.txt 2>&1; cat ../test_run_output.txt; rm test_candidate_temp.py`
- Bash: `rm -f test_run_output.txt` (cleanup)
- Bash: `rm -rf buggy/__pycache__` (remove pytest-created artifact, restore buggy/ to original state)
- Bash: `ls -la buggy/` (confirm buggy/ restored to only session_cache.py)
- Write: candidate_test.py (revised)
