"""
Adjudicator Agent — The Trust Gate.

This is the core innovation of Sentinel.
Every finding produced by specialist auditors must reference
at least one evidence_id from the deterministic evidence store.

Findings without evidence are DROPPED — not flagged, not warned about, DELETED.
This eliminates hallucinated security findings at the architecture level,
not the prompt level.
"""
import json
import uuid
from datetime import datetime, timezone
from sentinel.models.schemas import Finding, Evidence, Attestation
from pydantic import ValidationError


def adjudicate(
    candidate_findings: list[dict],
    evidence_store: list[dict],
    target_path: str,
) -> Attestation:
    """
    The trust gate. Takes raw candidate findings from LLM auditors
    and a list of deterministic evidence. Returns a clean Attestation
    where every surviving finding traces to real evidence.

    Args:
        candidate_findings: Raw dicts from LLM auditors (may be hallucinated)
        evidence_store: Verified Evidence objects from MCP tools
        target_path: Path to the scanned target

    Returns:
        Attestation with only evidence-backed findings
    """
    # Build lookup of valid evidence IDs
    valid_evidence_ids = set()
    validated_evidence = []

    for e in evidence_store:
        try:
            ev = Evidence(**e)
            valid_evidence_ids.add(ev.evidence_id)
            validated_evidence.append(ev)
        except (ValidationError, Exception):
            continue  # Malformed evidence is silently dropped

    # Adjudicate each candidate finding
    surviving_findings = []
    dropped_count = 0
    dropped_reasons = []

    for candidate in candidate_findings:
        # Check if it has evidence_ids field
        evidence_ids = candidate.get("evidence_ids", [])

        # Drop if no evidence_ids at all
        if not evidence_ids:
            dropped_count += 1
            dropped_reasons.append(
                f"DROPPED: '{candidate.get('title', 'unknown')}' — no evidence_ids"
            )
            continue

        # Drop if evidence_ids don't match any real evidence
        valid_refs = [eid for eid in evidence_ids if eid in valid_evidence_ids]
        if not valid_refs:
            dropped_count += 1
            dropped_reasons.append(
                f"DROPPED: '{candidate.get('title', 'unknown')}' "
                f"— evidence_ids {evidence_ids} not in evidence store"
            )
            continue

        # Only keep valid evidence references
        candidate["evidence_ids"] = valid_refs

        # Validate through Pydantic schema
        try:
            finding = Finding(**candidate)
            surviving_findings.append(finding)
        except ValidationError as e:
            dropped_count += 1
            dropped_reasons.append(
                f"DROPPED: '{candidate.get('title', 'unknown')}' "
                f"— schema validation failed: {e}"
            )

    # Determine verdict
    if not surviving_findings:
        verdict = "pass"
    elif any(f.severity in ("high", "critical") for f in surviving_findings):
        verdict = "fail"
    else:
        verdict = "pass_with_findings"

    # Build attestation
    attestation = Attestation(
        target=target_path,
        verdict=verdict,
        findings=surviving_findings,
        signature=f"sentinel-{uuid.uuid4().hex[:8]}",
        audit_ref=f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
    )

    # Print gate report (this is what you show in the demo)
    print("\n" + "="*60)
    print("SENTINEL ADJUDICATOR — TRUST GATE REPORT")
    print("="*60)
    print(f"Candidates received:  {len(candidate_findings)}")
    print(f"Evidence items:       {len(validated_evidence)}")
    print(f"Findings DROPPED:     {dropped_count}")
    print(f"Findings SURVIVING:   {len(surviving_findings)}")
    print(f"Verdict:              {verdict.upper()}")
    print("-"*60)
    if dropped_reasons:
        print("DROPPED FINDINGS:")
        for r in dropped_reasons:
            print(f"  ✗ {r}")
    if surviving_findings:
        print("SURVIVING FINDINGS:")
        for f in surviving_findings:
            print(f"  ✓ [{f.severity.upper()}] {f.title} (evidence: {f.evidence_ids})")
    print("="*60 + "\n")

    return attestation