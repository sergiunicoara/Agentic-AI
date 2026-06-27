"""
Supply Chain Auditor — Specialist for dependency vulnerabilities.
"""
from sentinel.models.schemas import Evidence


def audit_for_supply_chain(evidence_list: list[Evidence]) -> list[dict]:
    """
    Review evidence for supply chain vulnerabilities.
    Returns candidate findings — each MUST have evidence_ids.
    """
    candidates = []

    for ev in evidence_list:
        if ev.source != "pip_audit":
            continue

        vuln_id = ev.raw.get("vuln_id", "UNKNOWN")
        package = ev.raw.get("package", "unknown")
        version = ev.raw.get("version", "?")
        fix_versions = ev.raw.get("fix_versions", [])

        severity = "high" if vuln_id.startswith("CVE") else "med"

        candidate = {
            "finding_id": f"supply_{ev.evidence_id}",
            "pillar": 4,
            "severity": severity,
            "confidence": 0.98,
            "title": f"Dependency Vulnerability: {package}=={version} ({vuln_id})",
            "rationale": (
                f"pip-audit detected {vuln_id} in {package}=={version}. "
                f"{ev.raw.get('description', '')[:200]}"
            ),
            "evidence_ids": [ev.evidence_id],
            "remediation": (
                f"Upgrade {package} to one of: {fix_versions} "
                if fix_versions
                else f"Check {vuln_id} and upgrade {package} to a patched version."
            ),
        }
        candidates.append(candidate)

    return candidates