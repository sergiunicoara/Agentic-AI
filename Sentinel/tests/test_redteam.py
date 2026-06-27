"""
Red team tests — verifies injection surface detection.
"""
from sentinel.redteam.runner import run_red_team


def test_red_team_finds_surfaces_in_t1():
    """T1 has eval() and shell=True — red team must find them."""
    results = run_red_team("targets/t1_injection")
    assert results["successful_injections"] > 0
    assert results["injection_success_rate"] > 0


def test_red_team_clean_target_has_low_rate():
    """Clean target should have zero or very low injection success rate."""
    results = run_red_team("targets/c1_clean")
    assert results["injection_success_rate"] == 0.0


def test_red_team_produces_trajectory_evidence():
    """Red team must produce trajectory evidence for vulnerable targets."""
    results = run_red_team("targets/t1_injection")
    assert len(results["trajectory_evidence"]) > 0
    # Each evidence item must have required fields
    for ev in results["trajectory_evidence"]:
        assert ev["source"] == "redteam_trajectory"
        assert "ev_redteam_" in ev["evidence_id"]


def test_red_team_summary_structure():
    """Results must have all required summary fields."""
    results = run_red_team("targets/t1_injection")
    assert "total_payloads" in results
    assert "successful_injections" in results
    assert "injection_success_rate" in results
    assert "trajectory_evidence" in results
    assert results["total_payloads"] == 8  # corpus has 8 payloads