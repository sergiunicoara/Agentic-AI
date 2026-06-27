"""
Evidence Agent — Deterministic Evidence Collector.

Calls MCP tools (bandit, ruff, pip-audit) and converts their
raw output into structured Evidence objects with unique IDs.

No LLM judgment here. This agent produces only facts.
Every evidence item gets a unique ID that findings must reference.
"""
import uuid
from pathlib import Path
from sentinel.models.schemas import Evidence
from sentinel.mcp.evidence_server import security_scan, lint_scan, dependency_scan


def collect_evidence(target_path: str) -> list[Evidence]:
    """
    Run all deterministic tools against the target and return
    a list of Evidence objects with unique IDs.
    
    Args:
        target_path: Path to the target agent/repo to scan
        
    Returns:
        List of Evidence objects ready for the adjudicator
    """
    evidence_list = []
    target = Path(target_path)

    print(f"\n[EvidenceAgent] Scanning: {target_path}")
    print("-" * 50)

    # --- Run bandit security scan ---
    print("[EvidenceAgent] Running bandit security scan...")
    sec_result = security_scan(target_path)
    bandit_findings = sec_result.get("findings", [])
    print(f"[EvidenceAgent] bandit: {len(bandit_findings)} issues found")

    for issue in bandit_findings:
        ev = Evidence(
            evidence_id=f"ev_bandit_{uuid.uuid4().hex[:8]}",
            source="bandit",
            locator=f"{issue.get('filename', target_path)}:{issue.get('line_number', 0)}",
            raw={
                "test_id": issue.get("test_id"),
                "test_name": issue.get("test_name"),
                "issue_severity": issue.get("issue_severity"),
                "issue_confidence": issue.get("issue_confidence"),
                "issue_text": issue.get("issue_text"),
                "cwe_id": issue.get("issue_cwe", {}).get("id"),
            },
        )
        evidence_list.append(ev)
        print(f"  + {ev.evidence_id}: [{ev.raw['issue_severity']}] "
              f"{ev.raw['issue_text'][:60]} @ {ev.locator}")

    # --- Run ruff lint scan ---
    print("[EvidenceAgent] Running ruff lint scan...")
    lint_result = lint_scan(target_path)
    ruff_findings = lint_result.get("findings", [])
    print(f"[EvidenceAgent] ruff: {len(ruff_findings)} issues found")

    for issue in ruff_findings:
        ev = Evidence(
            evidence_id=f"ev_ruff_{uuid.uuid4().hex[:8]}",
            source="ruff",
            locator=f"{issue.get('filename', target_path)}:{issue.get('location', {}).get('row', 0)}",
            raw={
                "code": issue.get("code"),
                "message": issue.get("message"),
                "fix": issue.get("fix"),
            },
        )
        evidence_list.append(ev)

    # --- Run pip-audit dependency scan ---
    print("[EvidenceAgent] Running pip-audit dependency scan...")
    dep_result = dependency_scan(target_path)
    vulns = dep_result.get("vulnerabilities", [])
    
    # pip-audit returns a list of package dicts
    vuln_count = 0
    for pkg in vulns:
        if isinstance(pkg, dict):
            pkg_vulns = pkg.get("vulns", [])
            for vuln in pkg_vulns:
                ev = Evidence(
                    evidence_id=f"ev_pipaudit_{uuid.uuid4().hex[:8]}",
                    source="pip_audit",
                    locator=f"{pkg.get('name', 'unknown')}=={pkg.get('version', '?')}",
                    raw={
                        "package": pkg.get("name"),
                        "version": pkg.get("version"),
                        "vuln_id": vuln.get("id"),
                        "description": vuln.get("description", "")[:200],
                        "fix_versions": vuln.get("fix_versions", []),
                    },
                )
                evidence_list.append(ev)
                vuln_count += 1

    print(f"[EvidenceAgent] pip-audit: {vuln_count} vulnerabilities found")
    print(f"[EvidenceAgent] Total evidence collected: {len(evidence_list)}")
    print("-" * 50)

    return evidence_list