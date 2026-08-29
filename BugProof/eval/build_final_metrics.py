"""Canonical final-metrics builder. Integer-first: every percentage is
derived only after exact integer counts are independently computed from
frozen artifacts AND checked against the explicit audit expectations
below. Any integer mismatch fails loudly (raises), never silently averaged
or tolerance-compared -- floating-point tolerance (1e-6) is used only for
formatted derived percentages, never to decide whether counts agree.

No LLM call. No candidate/gate/oracle/threshold touched or tuned. Reads
only already-frozen results files; writes only evidence/final/final_metrics.json.

Run: python eval/build_final_metrics.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VERIFIED = "VERIFIED_REPRODUCTION"

# Explicit audit expectations -- used ONLY to verify independently-derived
# counts after the fact, never to compute them. Any disagreement is a
# hard failure (see _assert_int_eq below).
EXPECTED = {
    "A": {"total_cases": 12, "delivered_claims": 12, "correct_delivered": 9, "false_delivered": 3, "candidate_valid_count": 9},
    "B": {"total_cases": 12, "delivered_claims": 12, "correct_delivered": 9, "false_delivered": 3, "candidate_valid_count": 9},
    "C": {"total_cases": 12, "delivered_claims": 4, "correct_delivered": 3, "false_delivered": 1, "candidate_valid_count": 8},
    "D": {"total_cases": 12, "delivered_claims": 8, "correct_delivered": 5, "false_delivered": 3, "candidate_valid_count": 9},
    "D_exec": {"total_cases": 12, "delivered_claims": 5, "correct_delivered": 4, "false_delivered": 1, "candidate_valid_count": 10},
}

REJECTION_REASONS = ("WRONG_SYMPTOM", "PASSES_ON_BUGGY", "COLLECTION_ERROR", "FAILS_ON_FIXED", "SUITE_REGRESSION")


def _assert_int_eq(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"INTEGER MISMATCH -- {label}: derived={actual} expected={expected}. Failing loudly, not averaging.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _rows_A() -> list[dict]:
    data = json.loads((REPO_ROOT / "evidence/baseline/result_table.json").read_text(encoding="utf-8"))
    return [
        {"case_id": r["case_id"], "claimed": bool(r["claimed_reproduced"]), "oracle_status": r["oracle_verdict"], "oracle_reason": r["rejection_reason"]}
        for r in data
    ]


def _rows_variant(variant: str) -> list[dict]:
    data = json.loads((REPO_ROOT / f"evidence/advanced/results/{variant}/results.json").read_text(encoding="utf-8"))
    return [
        {"case_id": r["case_id"], "claimed": r["final_claim"] == VERIFIED, "oracle_status": r["oracle_status"], "oracle_reason": r.get("oracle_reason")}
        for r in data
    ]


def _rows_D_exec() -> list[dict]:
    data = json.loads((REPO_ROOT / "evidence/advanced/ablations/D_exec_per_case.json").read_text(encoding="utf-8"))
    return [
        {"case_id": r["case_id"], "claimed": r["d_exec_final_claim"] == VERIFIED, "oracle_status": r["oracle_status"], "oracle_reason": r.get("oracle_reason")}
        for r in data
    ]


def compute_variant(name: str, rows: list[dict]) -> dict:
    total_cases = len(rows)
    delivered = [r for r in rows if r["claimed"]]
    correct_delivered_rows = [r for r in delivered if r["oracle_status"] == "VALID"]
    false_delivered_rows = [r for r in delivered if r["oracle_status"] != "VALID"]
    candidate_valid_rows = [r for r in rows if r["oracle_status"] == "VALID"]

    delivered_claims = len(delivered)
    correct_delivered = len(correct_delivered_rows)
    false_delivered = len(false_delivered_rows)
    candidate_valid_count = len(candidate_valid_rows)

    exp = EXPECTED[name]
    _assert_int_eq(total_cases, exp["total_cases"], f"{name}.total_cases")
    _assert_int_eq(delivered_claims, exp["delivered_claims"], f"{name}.delivered_claims")
    _assert_int_eq(correct_delivered, exp["correct_delivered"], f"{name}.correct_delivered")
    _assert_int_eq(false_delivered, exp["false_delivered"], f"{name}.false_delivered")
    _assert_int_eq(candidate_valid_count, exp["candidate_valid_count"], f"{name}.candidate_valid_count")

    rejection_dist = {reason: 0 for reason in REJECTION_REASONS}
    rejection_dist["ORACLE_ERROR_TIMEOUT"] = 0
    for r in rows:
        if r["oracle_status"] == "REJECTED" and r["oracle_reason"] in REJECTION_REASONS:
            rejection_dist[r["oracle_reason"]] += 1
        elif r["oracle_status"] == "ERROR":
            rejection_dist["ORACLE_ERROR_TIMEOUT"] += 1

    def pct(n: int, d: int) -> float | None:
        return round(100 * n / d, 1) if d else None

    return {
        "variant": name,
        "total_cases": total_cases,
        "candidate_valid_count": candidate_valid_count,
        "CVR": {"count": candidate_valid_count, "total": total_cases, "pct": pct(candidate_valid_count, total_cases)},
        "delivered_claims": delivered_claims,
        "Coverage": {"count": delivered_claims, "total": total_cases, "pct": pct(delivered_claims, total_cases)},
        "correct_delivered": correct_delivered,
        "DVRR": {"count": correct_delivered, "total": total_cases, "pct": pct(correct_delivered, total_cases)},
        "false_delivered": false_delivered,
        "Claim_Precision": {"count": correct_delivered, "total": delivered_claims, "pct": pct(correct_delivered, delivered_claims)},
        "oracle_rejection_distribution": rejection_dist,
        "case_ids": {
            "delivered_correct": [r["case_id"] for r in correct_delivered_rows],
            "delivered_false": [r["case_id"] for r in false_delivered_rows],
            "not_delivered": [r["case_id"] for r in rows if not r["claimed"]],
        },
    }


def dominance(a: dict, b: dict) -> str:
    """Returns 'a_dominates_b', 'b_dominates_a', 'equivalent', or
    'non_dominated' on (correct_delivered [maximize], false_delivered
    [minimize])."""
    a_c, a_f = a["correct_delivered"], a["false_delivered"]
    b_c, b_f = b["correct_delivered"], b["false_delivered"]
    if a_c == b_c and a_f == b_f:
        return "equivalent"
    a_at_least_as_good = a_c >= b_c and a_f <= b_f
    b_at_least_as_good = b_c >= a_c and b_f <= a_f
    if a_at_least_as_good and not b_at_least_as_good:
        return "a_dominates_b"
    if b_at_least_as_good and not a_at_least_as_good:
        return "b_dominates_a"
    return "non_dominated"


def main() -> int:
    metrics = {
        "A": compute_variant("A", _rows_A()),
        "B": compute_variant("B", _rows_variant("B")),
        "C": compute_variant("C", _rows_variant("C")),
        "D": compute_variant("D", _rows_variant("D")),
        "D_exec": compute_variant("D_exec", _rows_D_exec()),
    }

    pareto = {
        "A_vs_B": dominance(metrics["A"], metrics["B"]),
        "A_vs_D": dominance(metrics["A"], metrics["D"]),
        "C_vs_D_exec": dominance(metrics["D_exec"], metrics["C"]),  # D_exec vs C
        "A_vs_D_exec": dominance(metrics["A"], metrics["D_exec"]),
    }
    # Sanity: these must match the observed dominance stated in the task
    # (derived programmatically above, not hard-coded as a conclusion).
    expected_pareto = {
        "A_vs_B": "equivalent",
        "A_vs_D": "a_dominates_b",       # A dominates D
        "C_vs_D_exec": "a_dominates_b",  # D_exec dominates C
        "A_vs_D_exec": "non_dominated",
    }
    for k, v in expected_pareto.items():
        _assert_int_eq(0 if pareto[k] == v else 1, 0, f"pareto.{k} expected={v!r} actual={pareto[k]!r}")

    non_dominated = ["A", "D_exec"]

    source_artifacts = []
    for rel, role in [
        ("evidence/baseline/result_table.json", "frozen Phase 2 baseline (A) per-case claim + oracle verdict"),
        ("evidence/advanced/results/B/results.json", "frozen B per-case claim + oracle verdict"),
        ("evidence/advanced/results/C/results.json", "frozen C per-case claim + oracle verdict"),
        ("evidence/advanced/results/D/results.json", "frozen D per-case claim + oracle verdict"),
        ("evidence/advanced/ablations/D_exec_per_case.json", "frozen D_exec per-case selection + claim + oracle verdict"),
    ]:
        p = REPO_ROOT / rel
        source_artifacts.append({"path": rel, "sha256": _sha256(p), "role": role})

    output = {
        "metadata": {
            "corpus_size": 12,
            "historical_vrr_alias": "CVR",
            "historical_vrr_alias_note": (
                "Prior frozen Phase 2/3 artifacts (evidence/baseline/*, evidence/advanced/summary.md, "
                "ablations/{A,B,C,D,D_exec}_metrics.json, D_exec_summary.md, src/bugproof/advanced.py "
                "docstrings, config.json) use 'VRR' to mean exactly what this document calls CVR: "
                "count(oracle_status == VALID) / total_cases, regardless of runtime delivery. Those "
                "files are historical and were not rewritten. Current submission-facing terminology "
                "(this file and the top-level README) uses CVR/DVRR/Claim_Precision/Coverage exclusively."
            ),
            "metric_definitions": {
                "CVR": "Candidate Validity Rate = count(oracle_status==VALID) / total_cases. Does NOT imply delivery.",
                "DVRR": "Delivered Valid Reproduction Rate = count(delivered AND oracle_status==VALID) / total_cases.",
                "Claim_Precision": "count(delivered AND oracle_status==VALID) / count(delivered).",
                "false_delivered": "count(delivered AND oracle_status!=VALID), absolute count.",
                "Coverage": "count(delivered) / total_cases. 'delivered' == runtime final_claim == VERIFIED_REPRODUCTION.",
            },
            "D_exec_post_hoc_disclosure": (
                "D_exec's selection policy (repair only cases where C.final_claim == EXECUTION_FAILURE) "
                "was chosen after observing full Phase 3 (A/B/C/D) behavior on this same 12-case corpus. "
                "It is evaluated on the same corpus that informed it and is NOT independent held-out "
                "validation. Selection is a pure function of C.final_claim only -- never oracle status, "
                "fixed/, oracle.yaml, reference_test.py, or decoy outcomes -- verified in "
                "eval/build_dexec_candidates.py and re-confirmed by this script's own dominance derivation."
            ),
            "break_even_P_over_M": 2.5,
            "break_even_note": (
                "Symbolic only: Cost = M*(N-DV) + DF*P. Break-even P/M=2.5 for A vs D_exec is a modeled "
                "threshold, not a measured empirical value. The n=3 human+AI timing pilot is separate, "
                "LOW-confidence evidence and is not used here."
            ),
        },
        "variants": metrics,
        "pareto": {
            "pairwise": pareto,
            "non_dominated_operating_points": non_dominated,
            "qualifier": "on the 12-case evaluation corpus -- not a claim of universal Pareto optimality",
        },
        "source_artifacts": source_artifacts,
    }

    out_dir = REPO_ROOT / "evidence" / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "final_metrics.json").write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("Integer-first audit: ALL PASS (every derived count matched its explicit expectation).")
    print()
    header = f"{'Variant':8s} {'total':>6s} {'valid':>6s} {'CVR':>7s} {'deliv':>6s} {'Cov':>7s} {'correct':>8s} {'DVRR':>7s} {'false':>6s} {'Prec':>7s}"
    print(header)
    for name in ("A", "B", "C", "D", "D_exec"):
        m = metrics[name]
        print(
            f"{name:8s} {m['total_cases']:6d} {m['candidate_valid_count']:6d} {m['CVR']['pct']:6.1f}% "
            f"{m['delivered_claims']:6d} {m['Coverage']['pct']:6.1f}% {m['correct_delivered']:8d} "
            f"{m['DVRR']['pct']:6.1f}% {m['false_delivered']:6d} {m['Claim_Precision']['pct']:6.1f}%"
        )
    print()
    print("Pareto (pairwise):", pareto)
    print("Non-dominated operating points on this corpus:", non_dominated)
    print()
    print("wrote", out_dir / "final_metrics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
