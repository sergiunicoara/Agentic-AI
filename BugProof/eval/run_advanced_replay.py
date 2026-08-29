"""Score frozen Phase 3 B/C/D candidates through the unmodified Phase 1
evaluator and emit the ablation metrics per variant. No LLM call happens
here -- this is the offline-reproducible half of Phase 3 (mirrors
eval/run_baseline_replay.py for Phase 2): a judge runs this and gets VRR
recomputed independently from the frozen candidates in
evidence/advanced/candidates/, with no API key and no network.

The runtime CLAIM per case/variant (VERIFIED_REPRODUCTION /
INSUFFICIENT_EVIDENCE / EXECUTION_FAILURE) is not something this script
recomputes -- it was decided live, by src/bugproof/advanced.py's
deterministic gate acting on real subagent output, at orchestration time
(see evidence/advanced/trajectories/<case>/bundle.json for the full
record of how). This script reads that already-decided claim back from
the trajectory bundle and treats it as fixed; what it DOES recompute,
fresh, is the oracle verdict for every frozen candidate -- exactly the
consistency check the Phase 3 plan requires: if this script's oracle
result for a candidate disagrees with what was recorded live during
orchestration, that is a bug to find, not a number to average away.

Regenerating the candidates themselves (the LLM half, for C and D-repair)
is not something a standalone script can offline-replay in this
environment -- see src/bugproof/baseline.py's module docstring for the
same constraint in Phase 2, and evidence/advanced/trajectories/ for the
recorded prompt + final message + workspace file contents of the run that
produced them.

Run: python eval/run_advanced_replay.py [--variant {B,C,D}]
Writes evidence/advanced/results/<variant>/results.json and
evidence/advanced/ablations/<variant>_metrics.json, prints a summary
table, and exits non-zero if any candidate's freshly-recomputed oracle
verdict disagrees with what the trajectory bundle recorded live.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bugproof.verdict import evaluate, load_oracle  # noqa: E402

CASES_DIR = REPO_ROOT / "cases"
ADVANCED_DIR = REPO_ROOT / "evidence" / "advanced"
CANDIDATES_DIR = ADVANCED_DIR / "candidates"
TRAJECTORIES_DIR = ADVANCED_DIR / "trajectories"
BASELINE_RESULT_TABLE = REPO_ROOT / "evidence" / "baseline" / "result_table.json"
BASELINE_USAGE = REPO_ROOT / "evidence" / "baseline" / "usage.json"

VARIANTS = ("A", "B", "C", "D")
VERIFIED = "VERIFIED_REPRODUCTION"


def _discover_cases() -> list[str]:
    return sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())


def _percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    idx = max(0, min(math.ceil(p * len(s)) - 1, len(s) - 1))
    return s[idx]


def _recorded_claim_and_bundle(case_id: str, variant: str) -> tuple[str, dict]:
    bundle = json.loads((TRAJECTORIES_DIR / case_id / "bundle.json").read_text(encoding="utf-8"))
    node = bundle[variant]
    return node["final_claim"], node


def _score_variant(variant: str, cases: list[str]) -> tuple[list[dict], list[str]]:
    rows = []
    mismatches = []
    for case_id in cases:
        case_dir = CASES_DIR / case_id
        candidate_path = CANDIDATES_DIR / variant / case_id / "candidate_test.py"
        oracle = load_oracle(case_dir)

        claim, node = _recorded_claim_and_bundle(case_id, variant)
        recorded_oracle_status = node["oracle_measurement"]["status"]
        recorded_oracle_reason = node["oracle_measurement"]["reason"]

        if not candidate_path.exists():
            rows.append({"case_id": case_id, "final_claim": claim, "oracle_status": "NO_CANDIDATE", "oracle_reason": None})
            continue

        verdict = evaluate(case_dir, candidate_path)

        if verdict.status != recorded_oracle_status or verdict.reason != recorded_oracle_reason:
            mismatches.append(
                f"{variant}/{case_id}: replay oracle={verdict.status}/{verdict.reason} "
                f"!= recorded {recorded_oracle_status}/{recorded_oracle_reason}"
            )

        rows.append(
            {
                "case_id": case_id,
                "difficulty": oracle.difficulty,
                "failure_family": oracle.failure_family,
                "final_claim": claim,
                "oracle_status": verdict.status,
                "oracle_reason": verdict.reason,
                "detail": verdict.detail[:500],
            }
        )
    return rows, mismatches


def _build_metrics(variant: str, rows: list[dict]) -> dict:
    n = len(rows)
    claim_count = sum(1 for r in rows if r["final_claim"] == VERIFIED)
    vrr_count = sum(1 for r in rows if r["oracle_status"] == "VALID")
    fcrr_num = sum(1 for r in rows if r["final_claim"] == VERIFIED and r["oracle_status"] != "VALID")

    reason_counts = {"VALID": vrr_count}
    for reason in ("WRONG_SYMPTOM", "PASSES_ON_BUGGY", "COLLECTION_ERROR", "FAILS_ON_FIXED", "SUITE_REGRESSION"):
        reason_counts[reason] = sum(1 for r in rows if r["oracle_status"] == "REJECTED" and r["oracle_reason"] == reason)
    reason_counts["ORACLE_ERROR_TIMEOUT"] = sum(1 for r in rows if r["oracle_status"] == "ERROR")

    return {
        "variant": variant,
        "n": n,
        "claim_rate": {"count": claim_count, "total": n, "pct": round(100 * claim_count / n, 1)},
        "vrr": {"count": vrr_count, "total": n, "pct": round(100 * vrr_count / n, 1)},
        "fcrr": {
            "count": fcrr_num,
            "claimed_total": claim_count,
            "pct": round(100 * fcrr_num / claim_count, 1) if claim_count else None,
        },
        "oracle_counts": reason_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("B", "C", "D"))
    args = parser.parse_args()
    variants = [args.variant] if args.variant else ["B", "C", "D"]

    cases = _discover_cases()
    all_mismatches: list[str] = []

    for variant in variants:
        rows, mismatches = _score_variant(variant, cases)
        all_mismatches.extend(mismatches)

        out_dir = ADVANCED_DIR / "results" / variant
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

        metrics = _build_metrics(variant, rows)
        (ADVANCED_DIR / "ablations").mkdir(parents=True, exist_ok=True)
        (ADVANCED_DIR / "ablations" / f"{variant}_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        print(
            f"{variant}: Claim {metrics['claim_rate']['count']}/{metrics['claim_rate']['total']}  "
            f"VRR {metrics['vrr']['count']}/{metrics['vrr']['total']}  "
            f"FCRR {metrics['fcrr']['count']}/{metrics['fcrr']['claimed_total']}"
        )

    if all_mismatches:
        print("\nMISMATCHES between live-recorded and freshly-replayed oracle verdicts:")
        for m in all_mismatches:
            print(" -", m)
        return 1

    print("\nAll replayed oracle verdicts match what was recorded live during orchestration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
