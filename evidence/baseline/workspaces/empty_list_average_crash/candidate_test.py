from stats import average_score


def test_average_score_empty_list_does_not_crash():
    """A brand-new quiz with no submitted scores should not crash the
    stats helper with a ZeroDivisionError. Averaging zero scores should
    be treated as "no data" (0) rather than raising.
    """
    assert average_score([]) == 0
