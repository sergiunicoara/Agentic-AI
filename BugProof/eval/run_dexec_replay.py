"""Offline replay for the D_exec ablation (post-hoc, evidence-driven: repair
only cases where C.final_claim == EXECUTION_FAILURE; C's VERIFIED_REPRODUCTION
and INSUFFICIENT_EVIDENCE outcomes pass through unchanged, INSUFFICIENT_EVIDENCE
receiving no repair at all). No LLM call -- scores the already-frozen
evidence/advanced/candidates/D_exec/ candidates (built entirely from existing
frozen C/D artifacts by evidence/advanced/_scratch_build_dexec.py, a pure
function of each case's C.final_claim) through the unmodified Phase 1
evaluator, exactly mirroring eval/run_advanced_replay.py's approach for
A/B/C/D but kept as a fully separate script so it can never touch those
frozen files.

Run: python eval/run_dexec_replay.py
Writes evidence/advanced/ablations/D_exec_metrics.json and
evidence/advanced/ablations/D_exec_per_case.json.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bugproof.verdict import evaluate, load_oracle  # noqa: E402

CASES_DIR = REPO_ROOT / "cases"
ADVANCED_DIR = REPO_ROOT / "evidence" / "advanced"
TRAJECTORIES_DIR = ADVANCED_DIR / "trajectories"
CANDIDATES_DIR = ADVANCED_DIR / "candidates" / "D_exec"

VERIFIED = "VERIFIED_REPRODUCTION"


def _discover_cases() -> list[str]:
    return sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())


def _percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    idx = max(0, min(math.ceil(p * len(s)) - 1, len(s) - 1))
    return s[idx]


def main() -> int:
    cases = _discover_cases()
    rows = []

    for case_id in cases:
        case_dir = CASES_DIR / case_id
        candidate_path = CANDIDATES_DIR / case_id / "candidate_test.py"
        oracle = load_oracle(case_dir)

        bundle = json.loads((TRAJECTORIES_DIR / case_id / "bundle.json").read_text(encoding="utf-8"))
        c_claim = bundle["C"]["final_claim"]
        selected_source = "D" if c_claim == "EXECUTION_FAILURE" else "C"
        final_claim = bundle["D"]["final_claim"] if selected_source == "D" else c_claim

        verdict = evaluate(case_dir, candidate_path)

        rows.append(
            {
                "case_id": case_id,
                "difficulty": oracle.difficulty,
                "failure_family": oracle.failure_family,
                "c_final_claim": c_claim,
                "selected_source": selected_source,
                "d_exec_final_claim": final_claim,
                "oracle_status": verdict.status,
                "oracle_reason": verdict.reason,
                "detail": verdict.detail[:500],
            }
        )

    n = len(rows)
    claim_count = sum(1 for r in rows if r["d_exec_final_claim"] == VERIFIED)
    vrr_count = sum(1 for r in rows if r["oracle_status"] == "VALID")
    fcrr_num = sum(1 for r in rows if r["d_exec_final_claim"] == VERIFIED and r["oracle_status"] != "VALID")

    reason_counts = {"VALID": vrr_count}
    for reason in ("WRONG_SYMPTOM", "PASSES_ON_BUGGY", "COLLECTION_ERROR", "FAILS_ON_FIXED", "SUITE_REGRESSION"):
        reason_counts[reason] = sum(1 for r in rows if r["oracle_status"] == "REJECTED" and r["oracle_reason"] == reason)
    reason_counts["ORACLE_ERROR_TIMEOUT"] = sum(1 for r in rows if r["oracle_status"] == "ERROR")

    metrics = {
        "variant": "D_exec",
        "n": n,
        "claim_rate": {"count": claim_count, "total": n, "pct": round(100 * claim_count / n, 1)},
        "vrr": {"count": vrr_count, "total": n, "pct": round(100 * vrr_count / n, 1)},
        "fcrr": {
            "count": fcrr_num,
            "claimed_total": claim_count,
            "pct": round(100 * fcrr_num / claim_count, 1) if claim_count else None,
        },
        "oracle_counts": reason_counts,
        "repair_eligible_cases": [r["case_id"] for r in rows if r["c_final_claim"] == "EXECUTION_FAILURE"],
        "cases_using_D_source": [r["case_id"] for r in rows if r["selected_source"] == "D"],
    }

    out_dir = ADVANCED_DIR / "ablations"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "D_exec_per_case.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out_dir / "D_exec_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"D_exec: Claim {claim_count}/{n}  VRR {vrr_count}/{n}  FCRR {fcrr_num}/{claim_count}")
    print("repair_eligible_cases (C.final_claim == EXECUTION_FAILURE):", metrics["repair_eligible_cases"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
