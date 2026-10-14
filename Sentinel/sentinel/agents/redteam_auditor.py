"""
Red Team Auditor — Specialist for adversarial trajectory evidence.

Converts redteam_trajectory evidence into candidate findings. Each
candidate MUST reference evidence_ids, same as every other auditor.

Trajectory evidence comes from two sources, distinguished by
raw["mode"]:
- "static" (sentinel.redteam.runner) — a payload's vector matched a
  textual pattern in the target's source (e.g. "eval(" present).
- "live" (sentinel.redteam.live_runner) — the payload was actually
  executed against the real function in a sandboxed subprocess. This is
  empirically confirmed code execution with attacker-controlled input,
  not a pattern match, so it gets higher confidence and a distinct title.
"""
from sentinel.models.schemas import Evidence

# Static vectors whose surface is direct code execution.
_HIGH_RISK_VECTORS = {"eval_surface", "subprocess_surface"}


def audit_for_redteam(evidence_list: list[Evidence]) -> list[dict]:
    """
    Review redteam_trajectory evidence and propose candidate findings.
    Returns candidate findings — each MUST have evidence_ids.
    """
    candidates = []

    for ev in evidence_list:
        if ev.source != "redteam_trajectory":
            continue

        payload_name = ev.raw.get("payload_name", "unknown payload")
        mode = ev.raw.get("mode", "static")

        if mode == "live":
            function = ev.raw.get("function", "the target function")
            sinks = ", ".join(ev.raw.get("sinks_hit", [])) or "a dangerous sink"
            title = f"Adversarial Surface LIVE-CONFIRMED: {payload_name}"
            severity = "high"
            confidence = 0.97
            rationale = (
                f"Red team payload '{payload_name}' was passed to {function} at "
                f"{ev.locator} in a hardened subprocess and was observed "
                f"reaching {sinks} with the attacker-controlled value — "
                f"an observed injection, not a static pattern match."
            )
        else:
            vector = ev.raw.get("vector", "unknown")
            title = f"Adversarial Surface (static match): {payload_name}"
            # A text match proves a surface exists, not that it's exploitable:
            # only direct code-execution surfaces are rated high.
            severity = "high" if vector in _HIGH_RISK_VECTORS else "med"
            confidence = 0.85 if vector in _HIGH_RISK_VECTORS else 0.6
            rationale = (
                f"Red team payload '{payload_name}' targeting the '{vector}' "
                f"vector matched a static attack surface at {ev.locator}. "
                f"This is a textual pattern match, not (yet) a live execution."
            )

        candidate = {
            "finding_id": f"redteam_{ev.evidence_id}",
            "pillar": 3,
            "severity": severity,
            "confidence": confidence,
            "title": title,
            "rationale": rationale,
            "evidence_ids": [ev.evidence_id],
            "remediation": (
                "Sanitize or remove the vulnerable surface identified by the "
                "red team payload before this target is deployed."
            ),
        }
        candidates.append(candidate)

    return candidates
