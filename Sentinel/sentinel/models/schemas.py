from pydantic import BaseModel, field_validator
from typing import Literal

# Pillar taxonomy (Finding.pillar). Maps each of the 7 OWASP-Agentic-style
# risk pillars Sentinel is designed to cover to the auditor that owns it.
# Pillars without an auditor yet are reserved for future specialists.
PILLARS: dict[int, str] = {
    1: "Identity & Access Boundaries",       # reserved — no auditor yet
    2: "Tool & Capability Misuse",           # reserved — no auditor yet
    3: "Prompt & Code Injection",            # InjectionAuditor, RedTeamAuditor
    4: "Supply Chain & Data Integrity",      # SupplyChainAuditor
    5: "Privilege & Confused Deputy",        # PrivilegeAuditor
    6: "Observability & Audit Trail",        # reserved — no auditor yet
    7: "Human Oversight & Containment",      # reserved — HITLGate is process, not a finding source
}

class Evidence(BaseModel):
    evidence_id: str
    source: Literal["ruff", "mypy", "bandit", "semgrep", "pip_audit", "redteam_trajectory"]
    locator: str
    raw: dict

class Finding(BaseModel):
    finding_id: str
    pillar: int
    severity: Literal["low", "med", "high", "critical"]
    confidence: float
    title: str
    rationale: str
    evidence_ids: list[str]
    remediation: str | None = None

    @field_validator("evidence_ids")
    @classmethod
    def must_have_evidence(cls, v):
        if not v:
            raise ValueError("Finding must reference at least one evidence_id")
        return v

    @field_validator("pillar")
    @classmethod
    def valid_pillar(cls, v):
        if v not in range(1, 8):
            raise ValueError("Pillar must be 1-7")
        return v

class Attestation(BaseModel):
    target: str
    verdict: Literal["pass", "pass_with_findings", "fail"]
    findings: list[Finding]
    signature: str
    audit_ref: str

class ScanRequest(BaseModel):
    target_path: str
    skills: list[str] = []
    red_team: bool = False
