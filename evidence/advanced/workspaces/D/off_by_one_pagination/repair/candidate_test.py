from paginator import get_page


def test_page_1_returns_first_three_items():
    # 10-item list, page size of 3, as described in report.md.
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    page_size = 3

    result = get_page(items, 1, page_size)

    # report.md states verbatim: "items 4, 5, 6 instead of 1, 2, 3" --
    # i.e. the correct/expected page-1 result is [1, 2, 3], and the bug
    # returns [4, 5, 6] instead.
    assert result == [1, 2, 3]


def test_page_2_returns_next_three_items():
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    page_size = 3

    result = get_page(items, 2, page_size)

    # report.md establishes (verbatim) that correct page 1 starts at the
    # value 1 ("... instead of 1, 2, 3") and that the page size is 3
    # ("a page size of 3"). Page 2 is the next consecutive page, so its
    # first value is 1 + page_size = 4, followed by 5 and 6.
    first = 1 + page_size
    assert result == [first, first + 1, first + 2]
