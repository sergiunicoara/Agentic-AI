"""Evaluate the frozen Phase 2 baseline candidates through the unmodified
Phase 1 evaluator. No LLM call happens here -- this is the offline-
reproducible half of Phase 2 (see R5): a judge runs this and gets the
headline VRR/FCRR numbers back from the already-recorded candidates in
evidence/baseline/candidates/, with no API key and no network.

Regenerating the candidates themselves (the LLM half) is not something a
standalone script can offline-replay in this environment -- see
src/bugproof/baseline.py's module docstring for why, and
evidence/baseline/trajectories/ for the recorded transcript of the one
run that produced them.

Run: python eval/run_baseline_replay.py
Writes evidence/baseline/results.json and prints the result table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bugproof.verdict import evaluate, load_oracle  # noqa: E402

CASES_DIR = REPO_ROOT / "cases"
CANDIDATES_DIR = REPO_ROOT / "evidence" / "baseline" / "candidates"
RESULTS_PATH = REPO_ROOT / "evidence" / "baseline" / "results.json"

REJECTION_REASONS = (
    "COLLECTION_ERROR",
    "PASSES_ON_BUGGY",
    "WRONG_SYMPTOM",
    "FAILS_ON_FIXED",
    "SUITE_REGRESSION",
)


def _discover_cases() -> list[str]:
    return sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())


def main() -> int:
    cases = _discover_cases()
    rows = []

    for case_id in cases:
        case_dir = CASES_DIR / case_id
        candidate_path = CANDIDATES_DIR / case_id / "candidate_test.py"

        if not candidate_path.exists():
            rows.append({"case_id": case_id, "status": "NO_CANDIDATE", "reason": None})
            continue

        oracle = load_oracle(case_dir)
        verdict = evaluate(case_dir, candidate_path)

        rows.append(
            {
                "case_id": case_id,
                "difficulty": oracle.difficulty,
                "failure_family": oracle.failure_family,
                "status": verdict.status,
                "reason": verdict.reason,
                "detail": verdict.detail[:500],
            }
        )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    header = ("case_id", "difficulty", "status", "reason")
    widths = [
        max(len(header[i]), max((len(str(r.get(header[i], ""))) for r in rows), default=0))
        for i in range(len(header))
    ]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        vals = [str(r.get(h, "") or "-") for h in header]
        print("  ".join(v.ljust(w) for v, w in zip(vals, widths)))

    valid = sum(1 for r in rows if r.get("status") == "VALID")
    print(f"\nVALID: {valid}/{len(rows)}")
    print(f"results written to {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
