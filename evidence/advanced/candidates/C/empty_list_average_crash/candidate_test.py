import pytest

from stats import average_score


def test_average_score_empty_list_raises_zero_division_error():
    """report.md: user created a new quiz with no scores yet, and the stats
    helper crashed with ZeroDivisionError while trying to average scores
    before any exist -- i.e. average_score([]) should raise ZeroDivisionError
    instead of returning something sane like 0."""
    with pytest.raises(ZeroDivisionError):
        average_score([])
