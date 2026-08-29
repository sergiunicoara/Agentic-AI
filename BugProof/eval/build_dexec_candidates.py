"""Offline construction of the D_exec ablation from already-frozen Phase 3
bundles. No LLM/agent call. Reads only C.final_claim to select a source per
case -- oracle status is never consulted during selection, enforced by
construction (this script never reads bundle['C']['oracle_measurement'] or
bundle['D']['oracle_measurement'] anywhere in the selection loop below).

Idempotent: writes evidence/advanced/candidates/D_exec/<case>/candidate_test.py
by copying the already-frozen C or D candidate for that case -- never
touches evidence/advanced/candidates/{A,B,C,D} or any Phase 0/1/2/3
artifact. Run once to (re)build D_exec's candidate set; then score it with
eval/run_dexec_replay.py (no LLM call either).

Run: python eval/build_dexec_candidates.py
"""

import json
import shutil
from pathlib import Path

REPO = Path(".")
TRAJ_DIR = REPO / "evidence/advanced/trajectories"
C_CANDIDATES = REPO / "evidence/advanced/candidates/C"
D_CANDIDATES = REPO / "evidence/advanced/candidates/D"
OUT_CANDIDATES = REPO / "evidence/advanced/candidates/D_exec"

cases = sorted(p.name for p in TRAJ_DIR.iterdir() if p.is_dir())

selection_rows = []
for cid in cases:
    bundle = json.loads((TRAJ_DIR / cid / "bundle.json").read_text(encoding="utf-8"))

    # --- Selection: pure function of C.final_claim ONLY. ---
    c_claim = bundle["C"]["final_claim"]
    if c_claim == "EXECUTION_FAILURE":
        selected_source = "D"
        selected_claim = bundle["D"]["final_claim"]
        src_candidate = D_CANDIDATES / cid / "candidate_test.py"
    else:
        selected_source = "C"
        selected_claim = c_claim
        src_candidate = C_CANDIDATES / cid / "candidate_test.py"
    # No read of bundle["C"]["oracle_measurement"] / bundle["D"]["oracle_measurement"]
    # occurred above -- selection is complete before any oracle field is touched.

    out_dir = OUT_CANDIDATES / cid
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_candidate, out_dir / "candidate_test.py")

    selection_rows.append(
        {
            "case_id": cid,
            "c_final_claim": c_claim,
            "selected_source": selected_source,
            "d_exec_final_claim": selected_claim,
        }
    )

Path("evidence/advanced/_scratch_dexec_selection.json").write_text(
    json.dumps(selection_rows, indent=2), encoding="utf-8"
)

for r in selection_rows:
    print(f"{r['case_id']:35s} C={r['c_final_claim']:22s} -> source={r['selected_source']}  D_exec_claim={r['d_exec_final_claim']}")

exec_failure_cases = [r["case_id"] for r in selection_rows if r["c_final_claim"] == "EXECUTION_FAILURE"]
print()
print("Cases repaired (selected_source == D):", [r["case_id"] for r in selection_rows if r["selected_source"] == "D"])
assert [r["case_id"] for r in selection_rows if r["selected_source"] == "D"] == exec_failure_cases, (
    "selected_source must equal 'D' iff c_final_claim == EXECUTION_FAILURE -- pure function check"
)
print("PASS: selected_source is confirmed a pure function of C.final_claim only.")
