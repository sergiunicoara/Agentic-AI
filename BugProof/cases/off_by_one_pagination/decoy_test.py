from paginator import get_page


def test_first_page_returns_first_three_items():
    items = list(range(1, 11))

    result = get_page(items, page_number=1, page_size=3)

    assert result == [4, 5, 6]
