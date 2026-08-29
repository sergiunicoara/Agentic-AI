from paginator import get_page


def test_page_one_returns_first_items():
    # 10-item list, page size 3.
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    # Page 1 (1-indexed) should return the first 3 items: 1, 2, 3.
    assert get_page(items, 1, 3) == [1, 2, 3]


def test_page_two_returns_next_items():
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    # Page 2 should return items 4, 5, 6.
    assert get_page(items, 2, 3) == [4, 5, 6]


def test_last_partial_page():
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    # Page 4 should return the final, partial page: items 10.
    assert get_page(items, 4, 3) == [10]
