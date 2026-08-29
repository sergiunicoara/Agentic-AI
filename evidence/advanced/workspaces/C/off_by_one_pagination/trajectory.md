# Trajectory

## What I read

- `report.md`: Describes a pagination bug. User asks for page 1 of a 10-item
  list with page size 3, and instead of items 1, 2, 3 they get items 4, 5, 6.
  They note "Page 2 looks off too" and aren't sure if the bug is in the
  pagination helper or in upstream slicing logic.

- `buggy/paginator.py`: The only file under `buggy/`. Contains a single
  function:

  ```python
  def get_page(items, page_number, page_size):
      """Return the slice of items for the given 1-indexed page."""
      start = page_number * page_size
      end = start + page_size
      return items[start:end]
  ```

## What I concluded

The docstring explicitly says `page_number` is 1-indexed. For a correct
1-indexed pagination, the start offset should be
`(page_number - 1) * page_size`, so that page 1 starts at index 0. Instead
the code computes `start = page_number * page_size`, which starts page 1 at
index `page_size` (skipping the first page_size items entirely) -- a classic
off-by-one error.

Concretely, for a 10-item list `[1..10]` with `page_size=3`:
- Page 1: buggy code computes `start = 1*3 = 3`, `end = 6`, so
  `items[3:6] == [4, 5, 6]` -- matching the report's observed "items 4, 5, 6
  instead of 1, 2, 3."
- Page 2: buggy code computes `start = 2*3 = 6`, `end = 9`, so
  `items[6:9] == [7, 8, 9]`, when the correct page 2 should be `[4, 5, 6]`
  (the items page 1 should have returned) -- matching the report's "Page 2
  looks off too."

This confirms the bug is in `get_page` itself (not "upstream slicing"): the
off-by-one is in the `start`/`end` arithmetic, missing the `- 1` needed to
convert the 1-indexed page number to a 0-indexed offset.

## What I wrote

`candidate_test.py` (in the working directory, sibling of `report.md` and
`buggy/`), importing `from paginator import get_page` (flat import, since
the test will be copied alongside `paginator.py` when run). Two tests:

1. `test_page_1_returns_first_three_items` -- asserts `get_page([1..10], 1, 3)
   == [1, 2, 3]`.
2. `test_page_2_returns_next_three_items` -- asserts `get_page([1..10], 2, 3)
   == [4, 5, 6]`.

## What happened when I ran it

Per the task instructions, I temporarily copied `candidate_test.py` into
`buggy/`, ran `python -m pytest candidate_test.py -v` from inside `buggy/`,
and observed:

```
candidate_test.py::test_page_1_returns_first_three_items FAILED
candidate_test.py::test_page_2_returns_next_three_items FAILED

AssertionError: assert [4, 5, 6] == [1, 2, 3]   (test 1)
AssertionError: assert [7, 8, 9] == [4, 5, 6]   (test 2)

2 failed in 1.18s
```

Both tests failed against the buggy code, with the actual returned values
exactly matching the off-by-one shift predicted by the source
(`get_page` returning items shifted one page_size ahead of the requested
page) -- reproducing the bug described in report.md.

After running, I removed the temporary copy of `candidate_test.py` from
`buggy/`, along with the `__pycache__` and `.pytest_cache` directories that
pytest created during the run, so that `buggy/paginator.py` is the only file
remaining in `buggy/`, byte-for-byte unchanged from its original state.

## Files read / commands run:

- Read `report.md`
- Read `buggy/paginator.py`
- Wrote `candidate_test.py` in the working directory
- `cp candidate_test.py buggy/candidate_test.py`
- `cd buggy && python -m pytest candidate_test.py -v` (2 failed, as shown above)
- `rm buggy/candidate_test.py`
- `rm -rf buggy/__pycache__ buggy/.pytest_cache .pytest_cache` (cleanup of
  artifacts created by the pytest run)
- `ls -la buggy/` to confirm only `paginator.py` remains
