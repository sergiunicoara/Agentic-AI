from stats import average_score


def test_average_of_no_scores_returns_none_instead_of_crashing():
    result = average_score([5])

    assert result is None
