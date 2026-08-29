def normalize_handle(raw):
    """Turn free-form display text into a canonical @handle."""
    return raw.strip().lower().replace(" ", "_")
