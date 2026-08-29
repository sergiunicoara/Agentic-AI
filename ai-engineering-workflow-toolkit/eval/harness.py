"""
Layer 5: Evaluation Harness

Runs the full review pipeline against every case in golden_dataset.json,
scores each output with the LLM-as-judge, and appends results to regression_log.jsonl.

Regression threshold: 4.0/5.0 composite score average across all cases.

Usage:
    python main.py eval
    python main.py eval --case GC-001
    python main.py eval --verbose
    python main.py eval --compare          # show delta vs previous run
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_GOLDEN_DATASET = _REPO_ROOT / "eval" / "golden_dataset.json"
_REGRESSION_LOG = _REPO_ROOT / "eval" / "regression_log.jsonl"
_REGRESSION_THRESHOLD = 4.0

# ANSI colours
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"


def _load_eval_log() -> list[dict]:
    if not _REGRESSION_LOG.exists():
        return []
    entries = []
    for line in _REGRESSION_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and '"cases_run"' in line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _delta_str(current: float, previous: float | None) -> str:
    if previous is None:
        return ""
    d = current - previous
    if abs(d) < 0.05:
        return f"  {_DIM}(±0.0){_RESET}"
    arrow = "↑" if d > 0 else "↓"
    colour = _GREEN if d > 0 else _RED
    return f"  {colour}({d:+.1f} {arrow}){_RESET}"


async def run_harness(
    case_id: str | None = None,
    verbose: bool = False,
    compare: bool = False,
) -> dict:
    """
    Run the evaluation harness.

    Returns summary dict with run_id, avg_composite, passed_threshold, results, etc.
    """
    from orchestrator.agent import OrchestratorAgent
    from review_agent.agent import ReviewAgent
    from eval.judge import judge

    golden_cases = json.loads(_GOLDEN_DATASET.read_text(encoding="utf-8"))

    if case_id:
        golden_cases = [c for c in golden_cases if c["id"] == case_id]
        if not golden_cases:
            raise ValueError(f"Case {case_id!r} not found in golden dataset.")

    # Load previous run for comparison
    prev_run: dict | None = None
    prev_by_case: dict[str, float] = {}
    if compare:
        history = _load_eval_log()
        if history:
            prev_run = history[-1]
            for pc in prev_run.get("per_case", []):
                prev_by_case[pc["case_id"]] = pc.get("composite_score", 0.0)

    run_id = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    compare_header = ""
    if compare and prev_run:
        prev_avg = prev_run.get("avg_composite", 0.0)
        compare_header = (
            f"  Comparing vs: {_DIM}{prev_run['run_id']}{_RESET}  "
            f"(prev avg: {prev_avg:.2f}/5.0)"
        )

    print(f"\n{'='*62}")
    print(f"  {_BOLD}AI Engineering Workflow Toolkit — Evaluation Harness{_RESET}")
    print(f"  Run ID: {_DIM}{run_id}{_RESET}")
    print(f"  Cases:  {len(golden_cases)}")
    if compare_header:
        print(compare_header)
    print(f"{'='*62}\n")

    orchestrator = OrchestratorAgent()
    reviewer = ReviewAgent()

    _CONCURRENCY = int(os.getenv("AIWT_EVAL_CONCURRENCY", "5"))
    sem = asyncio.Semaphore(_CONCURRENCY)
    print_lock = asyncio.Lock()

    case_results: list[dict | None] = [None] * len(golden_cases)

    async def _run_case(idx: int, case: dict) -> None:
        async with sem:
            case_start = time.monotonic()
            try:
                merged = await orchestrator.run(case["diff"], _REPO_ROOT)
                disposition = await reviewer.review(merged)
                score = judge(case["diff"], case["expected"], disposition)

                expected_verdict = case["expected"].get("verdict")
                forbidden = case["expected"].get("forbidden_verdicts", [])
                actual_verdict = disposition.get("verdict")
                verdict_correct = (
                    actual_verdict == expected_verdict
                    and actual_verdict not in forbidden
                )

                elapsed = time.monotonic() - case_start
                composite = score.get("composite", 0.0)

                result = {
                    "case_id": case["id"],
                    "description": case["description"],
                    "expected_verdict": expected_verdict,
                    "actual_verdict": actual_verdict,
                    "verdict_correct": verdict_correct,
                    "composite_score": composite,
                    "traceability": score.get("traceability"),
                    "accuracy": score.get("accuracy"),
                    "actionability": score.get("actionability"),
                    "rationale": score.get("rationale"),
                    "missed_findings": score.get("missed_findings", []),
                    "hallucinated_findings": score.get("hallucinated_findings", []),
                    "elapsed_ms": int(elapsed * 1000),
                    "run_id": run_id,
                }

                passed = composite >= _REGRESSION_THRESHOLD
                status_str = f"{_GREEN}PASS{_RESET}" if passed else f"{_RED}FAIL{_RESET}"
                verdict_flag = f"{_GREEN}[+]{_RESET}" if verdict_correct else f"{_RED}[!]{_RESET}"
                score_str = f"{composite:.1f}/5.0"

                delta = _delta_str(composite, prev_by_case.get(case["id"]))

                lines = [
                    f"  [{_CYAN}{case['id']}{_RESET}] "
                    f"{case['description'][:45]:<45} "
                    f"{status_str} ({score_str}) verdict {verdict_flag}"
                    f"{delta}"
                ]
                if verbose:
                    lines.append(
                        f"     Traceability: {score.get('traceability'):.1f}  "
                        f"Accuracy: {score.get('accuracy'):.1f}  "
                        f"Actionability: {score.get('actionability'):.1f}"
                    )
                    if score.get("missed_findings"):
                        lines.append(f"     {_YELLOW}Missed:{_RESET}       {score['missed_findings']}")
                    if score.get("hallucinated_findings"):
                        lines.append(f"     {_RED}Hallucinated:{_RESET}  {score['hallucinated_findings']}")

            except Exception as e:
                elapsed = time.monotonic() - case_start
                result = {
                    "case_id": case["id"],
                    "description": case["description"],
                    "error": str(e),
                    "composite_score": 0.0,
                    "elapsed_ms": int(elapsed * 1000),
                    "run_id": run_id,
                }
                lines = [f"  [{case['id']}] {case['description']}... {_RED}ERROR{_RESET} ({e})"]

            case_results[idx] = result
            async with print_lock:
                print("\n".join(lines), flush=True)

    await asyncio.gather(*[_run_case(i, c) for i, c in enumerate(golden_cases)])

    results = [r for r in case_results if r is not None]
    total_composite = sum(r.get("composite_score", 0.0) for r in results)
    avg_composite = total_composite / len(results) if results else 0.0
    passed_threshold = avg_composite >= _REGRESSION_THRESHOLD
    cases_passed = sum(1 for r in results if r.get("composite_score", 0) >= _REGRESSION_THRESHOLD)

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cases_run": len(results),
        "cases_passed": cases_passed,
        "avg_composite": round(avg_composite, 3),
        "passed_threshold": passed_threshold,
        "threshold": _REGRESSION_THRESHOLD,
        "results": results,
    }

    _append_regression_log(summary)

    # ── Summary banner ─────────────────────────────────────────────────────────
    avg_delta = ""
    if compare and prev_run:
        avg_delta = _delta_str(avg_composite, prev_run.get("avg_composite"))

    threshold_colour = _GREEN if passed_threshold else _RED
    status_word = f"{threshold_colour}{'PASSED' if passed_threshold else 'FAILED'}{_RESET}"

    print(f"\n{'='*62}")
    print(f"  Results:  {cases_passed}/{len(results)} passed")
    print(f"  Avg score: {_BOLD}{avg_composite:.2f}/5.0{_RESET}{avg_delta}")
    print(f"  Threshold ({_REGRESSION_THRESHOLD}/5.0): {status_word}")
    print(f"  Logged → {_DIM}{_REGRESSION_LOG}{_RESET}")
    print(f"{'='*62}\n")

    if not passed_threshold:
        print(
            f"  {_RED}[!]{_RESET} Regression threshold not met. Review failed cases and\n"
            f"      revise skills/prompts in Layer 1 before deployment.\n"
        )

    return summary


def _append_regression_log(summary: dict) -> None:
    _REGRESSION_LOG.parent.mkdir(exist_ok=True)
    log_entry = {
        "run_id": summary["run_id"],
        "timestamp": summary["timestamp"],
        "cases_run": summary["cases_run"],
        "cases_passed": summary["cases_passed"],
        "avg_composite": summary["avg_composite"],
        "passed_threshold": summary["passed_threshold"],
        "per_case": [
            {
                "case_id": r["case_id"],
                "composite_score": r.get("composite_score"),
                "verdict_correct": r.get("verdict_correct"),
                "elapsed_ms": r.get("elapsed_ms"),
            }
            for r in summary["results"]
        ],
    }
    with open(_REGRESSION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
