"""
Adjudicator Agent — The Trust Gate.

This is the core innovation of Sentinel.
Every finding produced by specialist auditors must reference
at least one evidence_id from the deterministic evidence store.

Findings without evidence are DROPPED — not flagged, not warned about, DELETED.
This eliminates hallucinated security findings at the architecture level,
not the prompt level.

Gate rules (a candidate survives only if ALL hold):
  1. It is a dict and cites at least one evidence_id.
  2. EVERY cited evidence_id exists in the evidence store (one fabricated id
     among real ones drops the whole finding).
  3. The cited evidence matches the finding:
     - if the finding names a `file`, every cited evidence item that has a
       file locator must point at that same file (pip_audit evidence, which
       locates a package not a file, is exempt);
     - pip_audit evidence can only support pillar 4 (Supply Chain), and
       redteam_trajectory evidence only pillar 3 (Injection). Other sources
       are not pillar-restricted (bandit/semgrep rules span several pillars).
  4. It validates against the Finding schema.

Verdict (fail closed): "inconclusive" whenever a required scanner did not
run cleanly or the target was invalid — never "pass" on an incomplete scan.

Signature: HMAC-SHA256 over the canonical JSON (sorted keys) of every
attestation field except the signature itself — target, verdict, findings,
cited evidence, tool status, audit_ref — keyed by SENTINEL_SIGNING_KEY. With
no key configured the signature is the literal "unsigned" (not
tamper-evident). verify_attestation() checks it.
"""
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePath
from sentinel.models.schemas import Finding, Evidence, Attestation
from pydantic import ValidationError

logger = logging.getLogger(__name__)

UNSIGNED = "unsigned"
SIGNING_KEY_ENV = "SENTINEL_SIGNING_KEY"

# Tool statuses that count as a clean run. "skipped" = nothing to scan
# (e.g. no requirements.txt) — recorded, but not a scan failure.
_OK_STATUSES = ("ok", "skipped")

# Evidence sources restricted to a single pillar (rule 3 above).
_SOURCE_PILLARS = {"pip_audit": {4}, "redteam_trajectory": {3}}


def optional_scanners() -> set[str]:
    """
    Scanners an operator has explicitly marked optional via
    SENTINEL_OPTIONAL_SCANNERS (comma-separated, e.g. "semgrep" on a host
    where it can't run). Their status is still recorded in the attestation;
    they just don't force an inconclusive verdict. Empty by default.
    """
    raw = os.environ.get("SENTINEL_OPTIONAL_SCANNERS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def inconclusive_reasons_for(tool_status: dict | None) -> list[str]:
    optional = optional_scanners()
    reasons = []
    for tool, st in sorted((tool_status or {}).items()):
        status = (st or {}).get("status", "error")
        if status not in _OK_STATUSES and tool not in optional:
            detail = (st or {}).get("detail", "")
            reasons.append(f"{tool}: {status}" + (f" ({detail[:200]})" if detail else ""))
    return reasons


def _locator_file(ev: Evidence) -> str | None:
    """File part of a 'path:line' locator, or None for non-file evidence."""
    if ev.source == "pip_audit":
        return None
    path, sep, tail = ev.locator.rpartition(":")
    # 'path:line', or 'path:function' for live red-team evidence
    if sep and path and (tail.isdigit() or ev.source == "redteam_trajectory"):
        return path
    return ev.locator


def _same_file(a: str, b: str) -> bool:
    """Case-insensitive path-suffix match, so a relative finding path
    ('targets/t1/agent.py' or 'agent.py') matches an absolute locator."""
    pa = PurePath(a.replace("\\", "/")).as_posix().lower().lstrip("./")
    pb = PurePath(b.replace("\\", "/")).as_posix().lower().lstrip("./")
    if not pa or not pb:
        return False
    return pa == pb or pa.endswith("/" + pb) or pb.endswith("/" + pa)


def _evidence_mismatch(candidate: dict, cited: list[Evidence]) -> str | None:
    pillar = candidate.get("pillar")
    for ev in cited:
        allowed = _SOURCE_PILLARS.get(ev.source)
        if allowed is not None and pillar not in allowed:
            return f"{ev.evidence_id} ({ev.source}) cannot support pillar {pillar}"
    finding_file = candidate.get("file")
    if finding_file:
        for ev in cited:
            ev_file = _locator_file(ev)
            if ev_file is not None and not _same_file(ev_file, str(finding_file)):
                return f"{ev.evidence_id} is in {ev_file}, finding names {finding_file}"
    return None


def _signing_payload(attestation: Attestation) -> bytes:
    data = attestation.model_dump(mode="json", exclude={"signature"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_attestation(attestation: Attestation) -> str:
    key = os.environ.get(SIGNING_KEY_ENV)
    if not key:
        logger.warning("%s is not set — attestation is UNSIGNED (not tamper-evident)",
                       SIGNING_KEY_ENV)
        return UNSIGNED
    mac = hmac.new(key.encode("utf-8"), _signing_payload(attestation), hashlib.sha256)
    return f"hmac-sha256:{mac.hexdigest()}"


def verify_attestation(attestation: Attestation | dict) -> bool:
    """
    True only if the attestation carries a valid HMAC-SHA256 signature under
    the current SENTINEL_SIGNING_KEY. Unsigned attestations, a missing key,
    or any modified field all return False.
    """
    if isinstance(attestation, dict):
        try:
            attestation = Attestation(**attestation)
        except ValidationError:
            return False
    key = os.environ.get(SIGNING_KEY_ENV)
    sig = attestation.signature or ""
    if not key or not sig.startswith("hmac-sha256:"):
        return False
    expected = hmac.new(key.encode("utf-8"), _signing_payload(attestation), hashlib.sha256)
    return hmac.compare_digest(sig, f"hmac-sha256:{expected.hexdigest()}")


def adjudicate(
    candidate_findings: list[dict],
    evidence_store: list[dict],
    target_path: str,
    on_progress=None,
    tool_status: dict | None = None,
    inconclusive_reasons: list[str] | None = None,
) -> Attestation:
    """
    The trust gate. Takes raw candidate findings from LLM auditors
    and a list of deterministic evidence. Returns a clean Attestation
    where every surviving finding traces to real evidence.

    Args:
        candidate_findings: Raw dicts from auditors (may be hallucinated)
        evidence_store: Verified Evidence objects from MCP tools
        target_path: Path to the scanned target
        tool_status: Per-scanner status from collect_evidence_with_status;
            any required scanner not ok => verdict "inconclusive"
        inconclusive_reasons: Extra reasons forcing "inconclusive"
            (e.g. an invalid target)

    Returns:
        Attestation with only evidence-backed findings
    """
    # Build lookup of valid evidence IDs
    evidence_by_id: dict[str, Evidence] = {}

    for e in evidence_store or []:
        try:
            ev = e if isinstance(e, Evidence) else Evidence(**e)
            evidence_by_id[ev.evidence_id] = ev
        except (ValidationError, TypeError):
            continue  # Malformed evidence is silently dropped

    # Adjudicate each candidate finding
    surviving_findings = []
    dropped_count = 0
    dropped_reasons = []

    def _drop(title, reason):
        nonlocal dropped_count
        dropped_count += 1
        dropped_reasons.append(f"DROPPED: '{title}' — {reason}")
        if on_progress:
            on_progress({"type": "gate_decision", "decision": "DROPPED",
                         "title": title, "reason": reason[:160]})

    for raw_candidate in candidate_findings or []:
        if not isinstance(raw_candidate, dict):
            _drop("unknown", f"candidate is not an object ({type(raw_candidate).__name__})")
            continue
        candidate = dict(raw_candidate)  # never mutate the caller's data
        title = candidate.get("title", "unknown")
        evidence_ids = candidate.get("evidence_ids", [])

        # Drop if no evidence_ids at all
        if not evidence_ids or not isinstance(evidence_ids, list):
            _drop(title, "no evidence_ids")
            continue

        # Drop if ANY cited id is not real evidence
        unknown = [eid for eid in evidence_ids if not isinstance(eid, str) or eid not in evidence_by_id]
        if unknown:
            _drop(title, f"evidence_ids not in evidence store: {unknown}")
            continue

        cited = [evidence_by_id[eid] for eid in evidence_ids]
        mismatch = _evidence_mismatch(candidate, cited)
        if mismatch:
            _drop(title, f"cited evidence does not match finding: {mismatch}")
            continue

        candidate["evidence_ids"] = list(dict.fromkeys(evidence_ids))

        # Validate through Pydantic schema
        try:
            finding = Finding(**candidate)
            surviving_findings.append(finding)
            if on_progress:
                on_progress({"type": "gate_decision", "decision": "SURVIVED",
                             "title": finding.title, "severity": finding.severity,
                             "evidence_ids": finding.evidence_ids})
        except (ValidationError, TypeError) as e:
            _drop(title, f"schema validation failed: {str(e)[:120]}")

    # Determine verdict — fail closed on an incomplete scan
    reasons = list(inconclusive_reasons or []) + inconclusive_reasons_for(tool_status)
    if reasons:
        verdict = "inconclusive"
    elif not surviving_findings:
        verdict = "pass"
    elif any(f.severity in ("high", "critical") for f in surviving_findings):
        verdict = "fail"
    else:
        verdict = "pass_with_findings"

    cited_ids = list(dict.fromkeys(eid for f in surviving_findings for eid in f.evidence_ids))

    # Build attestation
    attestation = Attestation(
        target=str(target_path),
        verdict=verdict,
        findings=surviving_findings,
        signature=UNSIGNED,
        audit_ref=f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        tool_status=tool_status or {},
        inconclusive_reasons=reasons,
        evidence=[evidence_by_id[eid] for eid in cited_ids],
    )
    attestation.signature = sign_attestation(attestation)

    if on_progress:
        on_progress({"type": "complete", "verdict": verdict,
                     "findings_count": len(surviving_findings),
                     "dropped_count": dropped_count,
                     "inconclusive_reasons": reasons,
                     "findings": [{"title": f.title, "severity": f.severity,
                                   "pillar": f.pillar, "evidence_ids": f.evidence_ids,
                                   "remediation": f.remediation}
                                  for f in surviving_findings]})

    # Print gate report (this is what you show in the demo)
    print("\n" + "="*60)
    print("SENTINEL ADJUDICATOR — TRUST GATE REPORT")
    print("="*60)
    print(f"Candidates received:  {len(candidate_findings or [])}")
    print(f"Evidence items:       {len(evidence_by_id)}")
    print(f"Findings DROPPED:     {dropped_count}")
    print(f"Findings SURVIVING:   {len(surviving_findings)}")
    print(f"Verdict:              {verdict.upper()}")
    print("-"*60)
    if reasons:
        print("INCONCLUSIVE — scan incomplete:")
        for r in reasons:
            print(f"  ! {r}")
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
