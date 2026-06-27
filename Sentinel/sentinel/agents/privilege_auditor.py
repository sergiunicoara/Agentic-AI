"""
Privilege Auditor — Specialist for IAM and confused deputy vulnerabilities.
"""
from sentinel.models.schemas import Evidence

PRIVILEGE_TEST_IDS = {
    "B105": ("hardcoded_password_string", "high", 5),
    "B106": ("hardcoded_password_funcarg", "high", 5),
    "B107": ("hardcoded_password_default", "high", 5),
    "B108": ("probable_temp_file", "low", 5),
}

PRIVILEGE_KEYWORDS = [
    "api_key", "secret_key", "password", "token",
    "credential", "AUTH_TOKEN", "BEARER",
]


def audit_for_privilege(evidence_list: list[Evidence]) -> list[dict]:
    """
    Review evidence for privilege and IAM vulnerabilities.
    Returns candidate findings — each MUST have evidence_ids.
    """
    candidates = []

    for ev in evidence_list:
        if ev.source != "bandit":
            continue

        test_id = ev.raw.get("test_id")
        if test_id not in PRIVILEGE_TEST_IDS:
            continue

        title, severity, pillar = PRIVILEGE_TEST_IDS[test_id]

        candidate = {
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
        }
        candidates.append(candidate)

    return candidates