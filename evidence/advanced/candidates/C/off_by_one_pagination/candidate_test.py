from paginator import get_page


def test_page_1_returns_first_three_items():
    # 10-item list, page size of 3, as described in report.md.
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    result = get_page(items, 1, 3)

    # Page 1 (1-indexed) of a page-size-3 pagination should return the
    # first three items: 1, 2, 3 -- not 4, 5, 6.
    assert result == [1, 2, 3]


def test_page_2_returns_next_three_items():
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    result = get_page(items, 2, 3)

    # Page 2 should pick up right where page 1 left off: items 4, 5, 6.
    assert result == [4, 5, 6]
