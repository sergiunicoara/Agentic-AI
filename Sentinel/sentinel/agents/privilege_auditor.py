"""
Privilege Auditor — Specialist for IAM and confused deputy vulnerabilities.

Two evidence sources feed this auditor:
- bandit: B105/B106/B107 match on variable *names* that look like
  passwords (password|pass|passwd|pwd|secret|token) — notably "key" is
  NOT in that list, so e.g. `PROVIDER_API_KEY = "sk-..."` slips past it.
- semgrep: sentinel-llm-api-key-hardcoded (project-authored) matches on
  the *value* format (sk-..., AIza..., ya29...) regardless of variable
  name, plus the p/gitleaks registry pack for known provider key formats.
  This is the auditor's actual ceiling raise beyond bandit.
"""
from sentinel.models.schemas import Evidence

PRIVILEGE_TEST_IDS = {
    "B105": ("hardcoded_password_string", "high", 5),
    "B106": ("hardcoded_password_funcarg", "high", 5),
    "B107": ("hardcoded_password_default", "high", 5),
    "B108": ("probable_temp_file", "low", 5),
}

# Semgrep check_id substrings that indicate hardcoded-credential findings.
SEMGREP_PRIVILEGE_PATTERNS = ("llm-api-key-hardcoded", "gitleaks", "secrets")


def audit_for_privilege(evidence_list: list[Evidence]) -> list[dict]:
    """
    Review evidence for privilege and IAM vulnerabilities.
    Returns candidate findings — each MUST have evidence_ids.
    """
    candidates = []

    for ev in evidence_list:
        if ev.source == "bandit":
            test_id = ev.raw.get("test_id")
            if test_id not in PRIVILEGE_TEST_IDS:
                continue
            title, severity, pillar = PRIVILEGE_TEST_IDS[test_id]
            candidates.append({
                "finding_id": f"priv_{ev.evidence_id}",
                "pillar": pillar,
                "severity": severity,
                "confidence": 0.9,
                "title": f"Credential Risk: {title.replace('_', ' ').title()}",
                "rationale": (
                    f"Bandit detected {test_id} at {ev.locator}. "
                    f"Hardcoded credentials create confused deputy vulnerabilities "
                    f"where agents may forward credentials to unintended services."
                ),
                "evidence_ids": [ev.evidence_id],
                "remediation": (
                    "Remove hardcoded credentials. Use environment variables "
                    "or a secrets manager. Inject credentials at runtime, "
                    "not through code."
                ),
            })

        elif ev.source == "semgrep":
            check_id = ev.raw.get("check_id", "")
            if not any(p in check_id for p in SEMGREP_PRIVILEGE_PATTERNS):
                continue
            candidates.append({
                "finding_id": f"priv_{ev.evidence_id}",
                "pillar": 5,
                "severity": "high",
                "confidence": 0.9,
                "title": "Credential Risk: Hardcoded API Key (value-format match)",
                "rationale": (
                    f"Semgrep detected {check_id} at {ev.locator}, matching a "
                    f"known credential value format independent of variable "
                    f"naming: {ev.raw.get('message', '')[:200]}"
                ),
                "evidence_ids": [ev.evidence_id],
                "remediation": (
                    "Remove hardcoded credentials. Use environment variables "
                    "or a secrets manager. Inject credentials at runtime, "
                    "not through code."
                ),
            })

    return candidates
