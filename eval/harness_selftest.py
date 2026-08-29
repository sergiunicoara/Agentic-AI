"""Proves the harness measures something before any agent code is trusted.

For every case under cases/:
  - reference_test.py must verify as VALID.
  - decoy_test.py (if present) must verify as REJECTED, with the reason
    recorded in oracle.yaml's decoy_expected_reason.
  - for cases flagged as twin decoys below, reference and decoy differ by
    one deliberate line -- if the verdict doesn't flip between them, the
    harness isn't discriminating anything and is not to be trusted.

Run: python eval/harness_selftest.py
Exits non-zero if anything is not as expected.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bugproof.verdict import evaluate, load_oracle, verify_fixed_suite_baseline  # noqa: E402

CASES_DIR = REPO_ROOT / "cases"

# Cases whose decoy_test.py is a near-copy of reference_test.py with one
# deliberate mutation, per BUGPROOF_AGENT_BRIEF.md Phase 0. At least two
# are required; the self-test fails loudly if fewer are found.
TWIN_DECOY_CASES = {
    "off_by_one_pagination",
    "empty_list_average_crash",
}


def _discover_cases() -> list[Path]:
    return sorted(p for p in CASES_DIR.iterdir() if p.is_dir())


def main() -> int:
    failures: list[str] = []
    rows: list[tuple[str, str, str, str, str]] = []  # case, ref verdict, decoy verdict, decoy reason, twin?

    case_dirs = _discover_cases()
    if not case_dirs:
        print(f"no cases found under {CASES_DIR}")
        return 1

    # Corpus-level invariant, checked once per case before any candidate is
    # evaluated against it: fixed/'s own native suite must collect and pass
    # on its own. evaluate() relies on this already being true -- it
    # attributes a native-suite test failing inside a candidate's combined
    # run to the candidate (SUITE_REGRESSION) without re-proving the native
    # suite was clean first. If it isn't, that attribution is unsound and
    # the case is not valid benchmark data; fail loudly here rather than
    # let every candidate against it produce a misleading verdict.
    for case_dir in case_dirs:
        baseline = verify_fixed_suite_baseline(case_dir)
        if not baseline.ok:
            failures.append(
                f"{case_dir.name}: fixed/ native suite does not pass on its own -- "
                f"{baseline.detail}"
            )

    for case_dir in case_dirs:
        case_id = case_dir.name
        oracle = load_oracle(case_dir)

        reference_path = case_dir / "reference_test.py"
        if not reference_path.exists():
            failures.append(f"{case_id}: missing reference_test.py")
            continue

        ref_verdict = evaluate(case_dir, reference_path)
        ref_status = f"{ref_verdict.status}" + (
            f" ({ref_verdict.reason})" if ref_verdict.reason else ""
        )
        if not ref_verdict.is_valid:
            failures.append(
                f"{case_id}: reference_test.py did not verify as VALID -- "
                f"got {ref_verdict.status} {ref_verdict.reason}: {ref_verdict.detail}"
            )

        decoy_path = case_dir / "decoy_test.py"
        decoy_status = "-"
        decoy_reason = "-"
        is_twin = "yes" if case_id in TWIN_DECOY_CASES else ""

        if decoy_path.exists():
            decoy_verdict = evaluate(case_dir, decoy_path)
            decoy_status = decoy_verdict.status
            decoy_reason = decoy_verdict.reason or "-"

            if decoy_verdict.status != "REJECTED":
                failures.append(
                    f"{case_id}: decoy_test.py did not verify as REJECTED -- "
                    f"got {decoy_verdict.status} ({decoy_verdict.reason})"
                )
            elif not oracle.decoy_expected_reason:
                failures.append(
                    f"{case_id}: decoy_test.py exists but oracle.yaml has no "
                    "decoy_expected_reason to check against"
                )
            elif decoy_verdict.reason != oracle.decoy_expected_reason:
                failures.append(
                    f"{case_id}: decoy_test.py rejected for {decoy_verdict.reason}, "
                    f"expected {oracle.decoy_expected_reason}"
                )

            if case_id in TWIN_DECOY_CASES:
                if not (ref_verdict.is_valid and decoy_verdict.status == "REJECTED"):
                    failures.append(
                        f"{case_id}: twin decoy did not flip the verdict "
                        f"(reference={ref_verdict.status}, decoy={decoy_verdict.status})"
                    )
        elif case_id in TWIN_DECOY_CASES:
            failures.append(f"{case_id}: listed as a twin-decoy case but has no decoy_test.py")

        rows.append((case_id, ref_status, decoy_status, decoy_reason, is_twin))

    found_twins = sum(1 for r in rows if r[4] == "yes")
    if found_twins < 2:
        failures.append(
            f"only {found_twins} twin-decoy case(s) found, need at least 2"
        )

    _print_table(rows)

    # No scratch-directory cleanup here, deliberately. run_pytest() already
    # keeps deletion out of the per-candidate hot path by renaming instead
    # of removing (see sandbox.py); a corpus-run-boundary sweep was tried
    # and reverted -- it still put an unbounded shutil.rmtree between "the
    # harness is done" and "the process actually exits", which is just the
    # same failure mode moved, not removed: a judge running this command
    # waits on the process to return, not on stdout to stop changing.
    # Cleanup is a separate, explicit operation: `python -m bugproof.cleanup`
    # or `make clean`. Evaluator correctness never depends on it running.
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"\nOK: {len(rows)} cases, {found_twins} twin decoys confirmed flipping the verdict.")
    return 0


def _print_table(rows: list[tuple[str, str, str, str, str]]) -> None:
    header = ("case_id", "reference", "decoy", "decoy_reason", "twin")
    widths = [
        max(len(header[i]), max((len(r[i]) for r in rows), default=0)) for i in range(len(header))
    ]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


if __name__ == "__main__":
    raise SystemExit(main())
