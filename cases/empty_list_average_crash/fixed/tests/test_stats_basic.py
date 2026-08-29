from stats import average_score


def test_average_of_three_scores():
    result = average_score([2, 4, 6])

    assert result == 4.0
