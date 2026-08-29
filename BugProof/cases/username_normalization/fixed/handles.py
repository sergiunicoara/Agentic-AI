import re


def normalize_handle(raw):
    """Turn free-form display text into a canonical @handle."""
    cleaned = re.sub(r"\s+", "_", raw.strip())
    return cleaned.lower()
