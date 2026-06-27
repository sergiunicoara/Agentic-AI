import pytest
from pydantic import ValidationError
from sentinel.models.schemas import Finding

def test_valid_finding():
    # 1. A valid Finding passes
    finding = Finding(
        finding_id="FIND-001",
        pillar=3,
        severity="high",
        confidence=0.9,
        title="Prompt Injection Vulnerability",
        rationale="System prompt concatenates user input directly.",
        evidence_ids=["EVID-001"],
        remediation="Use structured messages instead of format string."
    )
    assert finding.finding_id == "FIND-001"
    assert finding.pillar == 3
    assert finding.severity == "high"
    assert finding.evidence_ids == ["EVID-001"]

def test_empty_evidence_ids_raises_validation_error():
    # 2. A Finding with empty evidence_ids raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        Finding(
            finding_id="FIND-002",
            pillar=4,
            severity="med",
            confidence=0.8,
            title="Over-privileged Role",
            rationale="Agent has write permissions on system folder.",
            evidence_ids=[],  # Empty list should raise validation error
            remediation="Restrict scope."
        )
    assert "Finding must reference at least one evidence_id" in str(exc_info.value)

def test_invalid_pillar_raises_validation_error():
    # 3. A Finding with pillar=8 raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        Finding(
            finding_id="FIND-003",
            pillar=8,  # Invalid pillar (valid is 1-7)
            severity="low",
            confidence=0.7,
            title="Some Issue",
            rationale="Something is not right.",
            evidence_ids=["EVID-002"]
        )
    assert "Pillar must be 1-7" in str(exc_info.value)
