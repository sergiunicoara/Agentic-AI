# Trajectory

Read `report.md`: a 10-item list with page size 3 returns items 4, 5, 6 for
"page 1" instead of 1, 2, 3, and page 2 is also off.

Read `buggy/paginator.py`, which is the only file under `buggy/`:

```python
def get_page(items, page_number, page_size):
    """Return the slice of items for the given 1-indexed page."""
    start = page_number * page_size
    end = start + page_size
    return items[start:end]
```

The docstring says `page_number` is 1-indexed, but the slicing math treats it
as if it were 0-indexed (`start = page_number * page_size`). For page 1,
page_size 3: `start = 1*3 = 3`, `end = 6`, so `items[3:6]` yields the 4th,
5th, and 6th elements (values 4, 5, 6 in a 1..10 list) -- exactly the
off-by-one skip described in the report. The correct computation should be
`start = (page_number - 1) * page_size`.

Wrote `candidate_test.py` with three cases against the 1..10 list: page 1
should return [1,2,3], page 2 should return [4,5,6], and page 4 (the last,
partial page) should return [10]. All three encode the 1-indexed page
semantics stated in the docstring and expected by the report.

Ran the one allowed verification: copied `candidate_test.py` into `buggy/`,
ran `pytest` from there. All three tests failed against the current code:
page 1 returned [4,5,6], page 2 returned [7,8,9], and page 4 returned []
instead of [10] -- all consistent with the reported off-by-one bug. Removed
the temporary copy (and the `__pycache__` directory pytest created) from
`buggy/` afterward, leaving `buggy/paginator.py` as the only file, unchanged
from its original state.
