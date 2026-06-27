"""
Red Team Runner.

Tests a target agent's code against the injection corpus.
For each payload, checks whether the target's code contains
surfaces that would allow the injection to succeed.

This is static red-teaming — we analyze the attack surface
rather than executing live injections (which would require
a running target agent).
"""
import uuid
from pathlib import Path
from sentinel.redteam.corpus import get_all_payloads
from sentinel.models.schemas import Evidence


def _detect_vulnerable_surfaces(target_path: str) -> dict:
    """
    Scan target code for injection-vulnerable surfaces.
    Returns a map of vector → list of vulnerable locations.
    """
    surfaces = {
        "eval_surface": [],
        "subprocess_surface": [],
        "file_read_surface": [],
        "user_input": [],
        "tool_output": [],
    }

    target = Path(target_path)
    for py_file in target.rglob("*.py"):
        try:
            code = py_file.read_text(encoding="utf-8", errors="ignore")
            lines = code.splitlines()

            for i, line in enumerate(lines, 1):
                locator = f"{py_file}:{i}"

                if "eval(" in line and "ast.literal_eval" not in line:
                    surfaces["eval_surface"].append(locator)

                if "subprocess" in line and "shell=True" in line:
                    surfaces["subprocess_surface"].append(locator)

                if any(x in line for x in ["open(", "read_text(", "file_read"]):
                    surfaces["file_read_surface"].append(locator)

                if any(x in line for x in ["user_input", "input(", "request.data"]):
                    surfaces["user_input"].append(locator)

                if any(x in line for x in ["tool_result", "tool_output", "fetch("]):
                    surfaces["tool_output"].append(locator)

        except Exception:
            continue

    return surfaces


def run_red_team(target_path: str) -> dict:
    """
    Run the red team corpus against a target.
    Returns results with trajectory evidence.

    Args:
        target_path: Path to the target agent

    Returns:
        dict with results, trajectory evidence, and summary stats
    """
    print(f"\n[RedTeam] Starting red team assessment: {target_path}")
    print("-" * 50)

    # Detect vulnerable surfaces in target
    surfaces = _detect_vulnerable_surfaces(target_path)
    total_surfaces = sum(len(v) for v in surfaces.values())
    print(f"[RedTeam] Detected {total_surfaces} potentially vulnerable surfaces")

    payloads = get_all_payloads()
    results = []
    trajectory_evidence = []
    successful_injections = 0

    for payload in payloads:
        vector = payload["vector"]
        vulnerable_locations = surfaces.get(vector, [])

        # A payload "succeeds" if the target has a vulnerable surface
        # for that vector
        injection_succeeds = len(vulnerable_locations) > 0

        result = {
            "payload_id": payload["id"],
            "name": payload["name"],
            "vector": vector,
            "injection_succeeds": injection_succeeds,
            "vulnerable_locations": vulnerable_locations,
            "pillar": payload["pillar"],
        }
        results.append(result)

        if injection_succeeds:
            successful_injections += 1
            print(f"  [VULNERABLE] {payload['name']} → {vector} "
                  f"({len(vulnerable_locations)} surface(s))")

            # Create trajectory evidence
            ev = Evidence(
                evidence_id=f"ev_redteam_{uuid.uuid4().hex[:8]}",
                source="redteam_trajectory",
                locator=vulnerable_locations[0],
                raw={
                    "payload_id": payload["id"],
                    "payload_name": payload["name"],
                    "vector": vector,
                    "vulnerable_locations": vulnerable_locations,
                    "payload_preview": payload["payload"][:100],
                },
            )
            trajectory_evidence.append(ev)
        else:
            print(f"  [SAFE]      {payload['name']} → {vector} (no surface found)")

    total = len(payloads)
    success_rate = successful_injections / total if total > 0 else 0

    summary = {
        "target": target_path,
        "total_payloads": total,
        "successful_injections": successful_injections,
        "safe_count": total - successful_injections,
        "injection_success_rate": round(success_rate, 2),
        "results": results,
        "trajectory_evidence": [ev.model_dump() for ev in trajectory_evidence],
    }

    print(f"\n[RedTeam] Results: {successful_injections}/{total} payloads found surfaces")
    print(f"[RedTeam] Injection success rate: {success_rate:.0%}")
    print("-" * 50)

    return summary