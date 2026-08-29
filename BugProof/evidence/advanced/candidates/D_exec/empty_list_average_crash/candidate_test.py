import pytest

from stats import average_score


def test_average_score_empty_list_does_not_raise_zero_division_error():
    """report.md: user created a new quiz with no scores yet, and the stats
    helper crashed with ZeroDivisionError while trying to average scores
    before any exist. A fixed average_score([]) must not raise
    ZeroDivisionError just because there are no scores yet -- report.md
    does not say what value should come back instead, so this only checks
    that the crash described in the report is gone, without pinning an
    unverified replacement value."""
    average_score([])
