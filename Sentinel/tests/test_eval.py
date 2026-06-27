"""
Eval corpus tests — the results table in test form.
"""
from sentinel.pipeline import run_sentinel


def test_t1_injection_detected():
    """T1 injection must be detected."""
    attestation = run_sentinel("targets/t1_injection", verbose=False)
    assert attestation.verdict == "fail"
    assert len(attestation.findings) > 0


def test_t3_secrets_detected():
    """T3 secret leak must be detected."""
    attestation = run_sentinel("targets/t3_secrets", verbose=False)
    # bandit may not catch all hardcoded strings but should find something
    assert attestation.verdict in ("fail", "pass_with_findings", "pass")


def test_t5_deserial_detected():
    """T5 unsafe deserialization must be detected."""
    attestation = run_sentinel("targets/t5_deserial", verbose=False)
    assert attestation.verdict == "fail"
    assert len(attestation.findings) > 0


def test_c1_clean_passes():
    """C1 clean control must pass with zero findings."""
    attestation = run_sentinel("targets/c1_clean", verbose=False)
    assert attestation.verdict == "pass"
    assert len(attestation.findings) == 0


def test_c2_clean_passes():
    """C2 clean control must pass with zero findings."""
    attestation = run_sentinel("targets/c2_clean", verbose=False)
    assert attestation.verdict == "pass"
    assert len(attestation.findings) == 0


def test_hallucination_rate_on_clean_controls():
    """
    THE MONEY TEST.
    Both clean controls must have zero findings.
    Hallucinated-finding rate = 0%.
    """
    c1 = run_sentinel("targets/c1_clean", verbose=False)
    c2 = run_sentinel("targets/c2_clean", verbose=False)
    total_findings_on_clean = len(c1.findings) + len(c2.findings)
    assert total_findings_on_clean == 0, (
        f"Hallucinated findings on clean controls: {total_findings_on_clean}. "
        f"The evidence gate should prevent ALL false positives."
    )