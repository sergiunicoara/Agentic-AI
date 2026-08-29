def get_page(items, page_number, page_size):
    """Return the slice of items for the given 1-indexed page."""
    start = page_number * page_size
    end = start + page_size
    return items[start:end]
