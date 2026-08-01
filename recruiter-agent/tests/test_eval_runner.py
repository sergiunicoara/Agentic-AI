from app.ops.eval_runner import EvalCase, _state_issues


def test_golden_state_assertions_accept_matching_role_and_criteria():
    case = EvalCase(
        id="role-and-criteria",
        user_message="Senior ML Engineer with RAG",
        expected_role="Senior ML Engineer",
        expected_criteria=["production_rag", "ownership"],
    )

    assert not _state_issues(
        case,
        {"role": "Senior ML Engineer", "criteria": ["production_rag", "ownership"]},
    )


def test_golden_state_assertions_report_mismatch():
    case = EvalCase(
        id="mismatch",
        user_message="AI Engineer",
        expected_role="AI Engineer",
        expected_criteria=["leadership"],
    )

    issues = _state_issues(case, {"role": "Data Scientist", "criteria": []})
    assert len(issues) == 2
