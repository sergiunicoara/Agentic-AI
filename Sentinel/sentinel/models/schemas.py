from pydantic import BaseModel, field_validator
from typing import Literal

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
