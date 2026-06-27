"""
SARIF export — turns a Sentinel Attestation into a SARIF 2.1.0 log.

SARIF (Static Analysis Results Interchange Format) is the format GitHub
Code Scanning, Azure DevOps, and most CI security gates consume. Exporting
to it is what turns Sentinel from a demo into something a team can wire
into a pipeline: `sentinel-review --sarif report.sarif.json`.
"""
import json
from sentinel.models.schemas import Attestation, PILLARS

SARIF_SEVERITY_TO_LEVEL = {
    "low": "note",
    "med": "warning",
    "high": "error",
    "critical": "error",
}


def attestation_to_sarif(attestation: Attestation) -> dict:
    """
    Convert an Attestation into a SARIF 2.1.0 log dict.
    Every SARIF result traces back to the same evidence_ids the
    Attestation carries — nothing is added or inferred here.
    """
    rules = {}
    results = []

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
                "physicalLocation": {
                    "artifactLocation": {"uri": evidence_id},
                },
                "logicalLocations": [{"name": evidence_id, "kind": "evidence"}],
            })

        results.append({
            "ruleId": rule_id,
            "level": SARIF_SEVERITY_TO_LEVEL.get(finding.severity, "warning"),
            "message": {"text": f"{finding.title}\n\n{finding.rationale}"},
            "locations": locations or [{
                "physicalLocation": {"artifactLocation": {"uri": attestation.target}}
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
                "SRCROOT": {"uri": f"file:///{attestation.target}/"}
            },
            "results": results,
            "properties": {
                "verdict": attestation.verdict,
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
