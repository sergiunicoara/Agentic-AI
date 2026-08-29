# Trajectory

## What I read

- `report.md`: Describes two different test users seeing each other's cart
  items. User A calls the add-to-cart function with no cart passed in and
  adds "apple". Later, user B calls the same function, also with no cart
  passed in, and user B's cart already contains "apple" before user B added
  anything.
- `buggy/session_cache.py`: A single function,
  `add_item(item, cart=[])`, which appends `item` to `cart` and returns it.
  The default value for `cart` is a mutable list literal (`[]`) in the
  function signature.

## What I concluded

This is the classic Python "mutable default argument" pitfall. Default
argument values are evaluated exactly once, at function-definition time, and
the same list object is reused as the default on every call that doesn't
pass its own `cart` argument. So when user A calls `add_item("apple")`
without a cart, that shared default list gets `"apple"` appended to it. When
user B later calls `add_item("banana")`, also without a cart, they get the
very same shared list object back — which already contains `"apple"` from
user A's call — reproducing the "stale cache between users" bug described
in the report.

## Test written

`candidate_test.py` (in the working directory, sibling of `report.md` and
`buggy/`) imports `add_item` from `session_cache` (flat import, matching how
the file will be run once copied next to `session_cache.py`). It:

1. Calls `add_item("apple")` with no cart (simulating user A) and asserts
   the returned cart is `["apple"]`.
2. Calls `add_item("banana")` with no cart (simulating user B) and asserts
   the returned cart is `["banana"]` — i.e. that user B's cart should not
   contain user A's leftover "apple".

## What happened when I ran it

Per the task instructions, I temporarily copied `candidate_test.py` into
`buggy/`, ran it with pytest from inside `buggy/`, then deleted the copy
(and the `__pycache__`/`.pytest_cache` directories pytest created there) so
`buggy/` was restored to its original, byte-for-byte state (verified with
`ls -la` before and after — only `session_cache.py` remains).

Observed result: the test **FAILED**, as expected for the bug being
reproduced. Actual pytest output:

```
FAILED candidate_test.py::test_cart_not_shared_between_users_with_no_cart_passed_in

    assert cart_b == ["banana"]
E   AssertionError: assert ['apple', 'banana'] == ['banana']
E     At index 0 diff: 'apple' != 'banana'
E     Left contains one more item: 'banana'
E     Full diff:
E       [
E     +     'apple',
E           'banana',
E       ]

1 failed in 1.15s
```

This confirms the reported behavior: `cart_b` (user B's cart, from a call
with no cart argument) came back as `['apple', 'banana']` — it already
contained user A's `"apple"` before user B added anything — because both
calls shared the same mutable default list object.

## Files read / commands run:

- Read `report.md`
- Read `buggy/session_cache.py`
- `ls -la` on the working directory and `buggy/`
- `cp candidate_test.py buggy/candidate_test.py`
- `cd buggy && python -m pytest candidate_test.py -v` (observed 1 failed,
  as quoted above)
- `rm buggy/candidate_test.py`
- `rm -rf buggy/__pycache__ buggy/.pytest_cache`
- `ls -la buggy/` (confirmed only `session_cache.py` remains, matching the
  original state)
