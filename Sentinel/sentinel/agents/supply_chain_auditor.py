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
        aliases = [a for a in ev.raw.get("aliases", []) or [] if a != vuln_id]

        # Every pip-audit result is a published advisory (PYSEC / GHSA / CVE /
        # OSV) affecting the exact pinned version — a known-vulnerable
        # dependency is "high" regardless of which database's id came first.
        # (pip-audit carries no CVSS score; fix availability only changes
        # the remediation text, not the risk of the pinned version.)
        severity = "high"
        alias_text = f" (aliases: {', '.join(aliases[:5])})" if aliases else ""

        candidate = {
            "finding_id": f"supply_{ev.evidence_id}",
            "pillar": 4,
            "severity": severity,
            "confidence": 0.98,
            "title": f"Dependency Vulnerability: {package}=={version} ({vuln_id})",
            "rationale": (
                f"pip-audit detected {vuln_id}{alias_text} in {package}=={version}. "
                f"{ev.raw.get('description', '')[:200]}"
            ),
            "evidence_ids": [ev.evidence_id],
            "remediation": (
                f"Upgrade {package} to one of: {fix_versions} "
                if fix_versions
                else f"No fixed release of {package} is published for {vuln_id}; "
                     f"remove or replace the dependency, or mitigate per the advisory."
            ),
        }
        candidates.append(candidate)

    return candidates