def average_score(scores):
    """Return the mean of a list of numeric scores, or None if there are none yet."""
    if not scores:
        return None
    return sum(scores) / len(scores)
