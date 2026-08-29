"""Computation of user-delivery-perspective metrics (CVR, DVRR, Claim
Precision, False Delivered Claims, Coverage) for A/B/C/D/D_exec, from
already-frozen artifacts only. No LLM call. No candidate/claim/gate/oracle
touched -- this script only reads existing results.json / result_table.json
/ D_exec_per_case.json files and computes new numbers from them.

CVR (Candidate Validity Rate) is the same formula previously labeled "VRR"
in evidence/advanced/ablations/{A,B,C,D}_metrics.json: count(oracle_status
== VALID) / total_cases, regardless of whether the runtime system actually
claimed that case. Renamed here, not redefined -- those frozen files are
untouched; this is a delivery-perspective re-labeling for a new audit, not
a correction.

Run: python eval/compute_delivery_audit.py
Writes evidence/advanced/ablations/delivery_audit_metrics.json.
"""

import json
from pathlib import Path

REPO = Path(".")
VERIFIED = "VERIFIED_REPRODUCTION"


def rows_A():
    data = json.loads((REPO / "evidence/baseline/result_table.json").read_text(encoding="utf-8"))
    return [
        {"case_id": r["case_id"], "claimed": bool(r["claimed_reproduced"]), "oracle_status": r["oracle_verdict"]}
        for r in data
    ]


def rows_variant(variant):
    data = json.loads((REPO / f"evidence/advanced/results/{variant}/results.json").read_text(encoding="utf-8"))
    return [
        {"case_id": r["case_id"], "claimed": r["final_claim"] == VERIFIED, "oracle_status": r["oracle_status"]}
        for r in data
    ]


def rows_D_exec():
    data = json.loads((REPO / "evidence/advanced/ablations/D_exec_per_case.json").read_text(encoding="utf-8"))
    return [
        {"case_id": r["case_id"], "claimed": r["d_exec_final_claim"] == VERIFIED, "oracle_status": r["oracle_status"]}
        for r in data
    ]


def compute(variant_name, rows):
    n = len(rows)
    delivered = [r for r in rows if r["claimed"]]
    delivered_valid = [r for r in delivered if r["oracle_status"] == "VALID"]
    delivered_false = [r for r in delivered if r["oracle_status"] != "VALID"]
    cvr_valid = [r for r in rows if r["oracle_status"] == "VALID"]  # oracle-VALID regardless of claim -- CVR (was VRR)

    cvr_count = len(cvr_valid)
    dvrr_count = len(delivered_valid)
    false_delivered_count = len(delivered_false)
    coverage_count = len(delivered)
    claim_precision_num = dvrr_count
    claim_precision_den = coverage_count

    return {
        "variant": variant_name,
        "n": n,
        "CVR": {"count": cvr_count, "total": n, "pct": round(100 * cvr_count / n, 1)},
        "DVRR": {"count": dvrr_count, "total": n, "pct": round(100 * dvrr_count / n, 1)},
        "claim_precision": {
            "count": claim_precision_num,
            "total": claim_precision_den,
            "pct": round(100 * claim_precision_num / claim_precision_den, 1) if claim_precision_den else None,
        },
        "false_delivered_claims": {"count": false_delivered_count},
        "coverage": {"count": coverage_count, "total": n, "pct": round(100 * coverage_count / n, 1)},
        "delivered_valid_case_ids": [r["case_id"] for r in delivered_valid],
        "false_delivered_case_ids": [r["case_id"] for r in delivered_false],
        "not_delivered_case_ids": [r["case_id"] for r in rows if not r["claimed"]],
    }


results = {}
results["A"] = compute("A", rows_A())
for v in ("B", "C", "D"):
    results[v] = compute(v, rows_variant(v))
results["D_exec"] = compute("D_exec", rows_D_exec())

out_path = REPO / "evidence/advanced/ablations/delivery_audit_metrics.json"
out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

header = f"{'Variant':8s} {'CVR':>12s} {'DVRR':>12s} {'Precision':>12s} {'FalseDeliv':>11s} {'Coverage':>12s}"
print(header)
for v in ("A", "B", "C", "D", "D_exec"):
    m = results[v]
    print(
        f"{v:8s} "
        f"{m['CVR']['count']}/{m['CVR']['total']}={m['CVR']['pct']:5.1f}%  "
        f"{m['DVRR']['count']}/{m['DVRR']['total']}={m['DVRR']['pct']:5.1f}%  "
        f"{m['claim_precision']['count']}/{m['claim_precision']['total']}={m['claim_precision']['pct']}%  "
        f"{m['false_delivered_claims']['count']:^10d} "
        f"{m['coverage']['count']}/{m['coverage']['total']}={m['coverage']['pct']:5.1f}%"
    )

print()
print("wrote evidence/advanced/ablations/delivery_audit_metrics.json")
