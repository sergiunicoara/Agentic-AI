from paginator import get_page


def test_second_page_of_ten_items():
    items = list(range(1, 11))

    result = get_page(items, page_number=2, page_size=3)

    assert result == [4, 5, 6]


def test_last_partial_page():
    items = list(range(1, 11))

    result = get_page(items, page_number=4, page_size=3)

    assert result == [10]
