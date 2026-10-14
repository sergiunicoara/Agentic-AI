"""
SARIF export — turns a Sentinel Attestation into a SARIF 2.1.0 log.

SARIF (Static Analysis Results Interchange Format) is the format GitHub
Code Scanning, Azure DevOps, and most CI security gates consume. Exporting
to it is what turns Sentinel from a demo into something a team can wire
into a pipeline: `sentinel-review --sarif report.sarif.json`.
"""
import json
from pathlib import Path
from sentinel.models.schemas import Attestation, Evidence, PILLARS

SARIF_SEVERITY_TO_LEVEL = {
    "low": "note",
    "med": "warning",
    "high": "error",
    "critical": "error",
}


def _scan_root() -> Path:
    from sentinel.mcp.evidence_server import SCAN_ROOT
    return SCAN_ROOT


def _physical_location(ev: Evidence | None, attestation: Attestation) -> dict:
    """
    SARIF physicalLocation for one piece of evidence: the real file (relative
    to SRCROOT = the scan root when inside it) and start line. pip-audit
    evidence locates a package, so it points at the target's requirements.txt.
    Falls back to the target directory when the evidence isn't available.
    """
    target_uri = attestation.target.rstrip("/") or "."
    if ev is None:
        return {"artifactLocation": {"uri": target_uri, "uriBaseId": "SRCROOT"}}
    if ev.source == "pip_audit":
        return {"artifactLocation": {"uri": f"{target_uri}/requirements.txt",
                                     "uriBaseId": "SRCROOT"}}

    path, sep, tail = ev.locator.rpartition(":")
    line = int(tail) if sep and tail.isdigit() else None
    file_part = path if line is not None or (sep and ev.source == "redteam_trajectory") else ev.locator
    p = Path(file_part)
    location: dict
    if p.is_absolute():
        try:
            location = {"uri": p.resolve().relative_to(_scan_root()).as_posix(),
                        "uriBaseId": "SRCROOT"}
        except ValueError:
            location = {"uri": p.as_uri()}
    else:
        location = {"uri": p.as_posix(), "uriBaseId": "SRCROOT"}

    physical = {"artifactLocation": location}
    if line and line > 0:
        physical["region"] = {"startLine": line}
    return physical


def attestation_to_sarif(attestation: Attestation) -> dict:
    """
    Convert an Attestation into a SARIF 2.1.0 log dict.
    Every SARIF result traces back to the same evidence_ids the
    Attestation carries — nothing is added or inferred here.
    """
    rules = {}
    results = []
    evidence_by_id = {ev.evidence_id: ev for ev in attestation.evidence}

    for finding in attestation.findings:
        rule_id = f"sentinel/pillar-{finding.pillar}"
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": PILLARS.get(finding.pillar, f"Pillar {finding.pillar}"),
                "shortDescription": {
                    "text": PILLARS.get(finding.pillar, f"Pillar {finding.pillar}")
                },
                "fullDescription": {
                    "text": (
                        f"Findings in Sentinel risk pillar {finding.pillar}: "
                        f"{PILLARS.get(finding.pillar, 'unnamed pillar')}"
                    )
                },
                "defaultConfiguration": {"level": "warning"},
            }

        locations = []
        for evidence_id in finding.evidence_ids:
            locations.append({
                "physicalLocation": _physical_location(evidence_by_id.get(evidence_id), attestation),
                "logicalLocations": [{"name": evidence_id, "kind": "evidence"}],
            })

        results.append({
            "ruleId": rule_id,
            "level": SARIF_SEVERITY_TO_LEVEL.get(finding.severity, "warning"),
            "message": {"text": f"{finding.title}\n\n{finding.rationale}"},
            "locations": locations or [{
                "physicalLocation": _physical_location(None, attestation)
            }],
            "properties": {
                "sentinel_finding_id": finding.finding_id,
                "confidence": finding.confidence,
                "evidence_ids": finding.evidence_ids,
                "remediation": finding.remediation,
            },
        })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Sentinel",
                    "informationUri": "https://github.com/sergiunicoara/Agentic-AI",
                    "rules": list(rules.values()),
                }
            },
            "originalUriBaseIds": {
                "SRCROOT": {"uri": _scan_root().as_uri() + "/"}
            },
            "results": results,
            "properties": {
                "verdict": attestation.verdict,
                "inconclusive_reasons": attestation.inconclusive_reasons,
                "tool_status": attestation.tool_status,
                "audit_ref": attestation.audit_ref,
                "signature": attestation.signature,
            },
        }],
    }


def write_sarif(attestation: Attestation, output_path: str) -> None:
    """Write a SARIF log for the given attestation to output_path."""
    sarif_log = attestation_to_sarif(attestation)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sarif_log, f, indent=2)
