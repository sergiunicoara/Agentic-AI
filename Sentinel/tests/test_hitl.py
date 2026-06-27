"""
HITL gate tests.
"""
from sentinel.agents.hitl_gate import HITLGate
from sentinel.models.schemas import Finding


def _make_finding(severity: str, title: str) -> Finding:
    return Finding(
        finding_id=f"test_{title[:10]}",
        pillar=3,
        severity=severity,
        confidence=0.9,
        title=title,
        rationale="Test finding",
        evidence_ids=["ev_test_001"],
        remediation="Fix it.",
    )


def test_hitl_no_findings_returns_no_action():
    """Empty findings list needs no approval."""
    gate = HITLGate()
    result = gate.request_approval([], "targets/test", interactive=False)
    assert result["status"] == "no_action_required"


def test_hitl_high_severity_requires_approval():
    """High severity findings go to pending in non-interactive mode."""
    gate = HITLGate()
    findings = [_make_finding("high", "Shell injection")]
    result = gate.request_approval(findings, "targets/t1", interactive=False)
    assert result["status"] == "pending"
    assert len(result["approval_log"]) == 1
    assert result["approval_log"][0]["decision"] == "pending"


def test_hitl_auto_approves_low_severity():
    """Low severity is auto-approved when configured."""
    gate = HITLGate(auto_approve_low=True)
    findings = [_make_finding("low", "Minor style issue")]
    result = gate.request_approval(findings, "targets/t1", interactive=False)
    assert len(result["approved"]) == 1
    assert result["approval_log"][0]["decision"] == "auto_approved"


def test_hitl_audit_log_is_append_only():
    """Every decision must be logged."""
    gate = HITLGate(auto_approve_low=True)
    findings = [
        _make_finding("low", "Low issue"),
        _make_finding("high", "High issue"),
    ]
    result = gate.request_approval(findings, "targets/t1", interactive=False)
    assert len(result["approval_log"]) == 2


def test_hitl_mixed_severity():
    """Low auto-approved, high goes pending."""
    gate = HITLGate(auto_approve_low=True)
    findings = [
        _make_finding("low", "Low issue"),
        _make_finding("high", "High issue"),
    ]
    result = gate.request_approval(findings, "targets/t1", interactive=False)
    assert len(result["approved"]) == 1
    assert result["approved"][0].severity == "low"
    pending = [l for l in result["approval_log"] if l["decision"] == "pending"]
    assert len(pending) == 1