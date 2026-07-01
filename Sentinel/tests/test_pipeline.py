"""
Integration test — full pipeline end-to-end.
"""
from sentinel.pipeline import run_sentinel


def test_pipeline_finds_issues_in_t1():
    """Full pipeline on T1 must return fail verdict with findings."""
    attestation = run_sentinel("targets/t1_injection", verbose=False)
    assert attestation.verdict == "fail"
    assert len(attestation.findings) == 2
    assert [f.title for f in attestation.findings] == [
        "Unsafe eval() of user input",
        "Shell injection via subprocess",
    ]
    # Every finding must have evidence
    for f in attestation.findings:
        assert len(f.evidence_ids) > 0


def test_pipeline_passes_clean_target():
    """Full pipeline on clean target must return pass verdict."""
    attestation = run_sentinel("targets/c1_clean", verbose=False)
    assert attestation.verdict == "pass"
    assert len(attestation.findings) == 0


def test_pipeline_produces_attestation():
    """Attestation must have signature and audit_ref."""
    attestation = run_sentinel("targets/t1_injection", verbose=False)
    assert attestation.signature.startswith("sentinel-")
    assert attestation.audit_ref.startswith("audit-")
    assert attestation.target == "targets/t1_injection"
