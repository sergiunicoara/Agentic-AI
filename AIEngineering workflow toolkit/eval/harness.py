"""
Layer 5: Evaluation Harness

Runs the full review pipeline against every case in golden_dataset.json,
scores each output with the LLM-as-judge, and appends results to regression_log.jsonl.

Regression threshold: 4.0/5.0 composite score average across all cases.

Usage:
    python main.py eval
    python main.py eval --case GC-001
    python main.py eval --verbose
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


async def run_harness(
    case_id: str | None = None,
    verbose: bool = False,
) -> dict:
    """
    Run the evaluation harness.

    Returns:
    {
        "run_id": str,
        "timestamp": str,
        "cases_run": int,
        "cases_passed": int,
        "avg_composite": float,
        "passed_threshold": bool,
        "results": [...]
    }
    """
    from orchestrator.agent import OrchestratorAgent
    from review_agent.agent import ReviewAgent
    from eval.judge import judge

    golden_cases = json.loads(_GOLDEN_DATASET.read_text(encoding="utf-8"))

    if case_id:
        golden_cases = [c for c in golden_cases if c["id"] == case_id]
        if not golden_cases:
            raise ValueError(f"Case {case_id!r} not found in golden dataset.")

    run_id = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    results = []
    total_composite = 0.0

    print(f"\n{'='*60}")
    print(f"  AI Engineering Workflow Toolkit — Evaluation Harness")
    print(f"  Run ID: {run_id}")
    print(f"  Cases:  {len(golden_cases)}")
    print(f"{'='*60}\n")

    orchestrator = OrchestratorAgent()
    reviewer = ReviewAgent()

    # Semaphore limits concurrent pipeline executions to avoid API rate limits
    _CONCURRENCY = int(os.getenv("AIWT_EVAL_CONCURRENCY", "5"))
    sem = asyncio.Semaphore(_CONCURRENCY)
    print_lock = asyncio.Lock()

    # results[idx] is filled by each task; None until complete
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

                status = "PASS" if composite >= _REGRESSION_THRESHOLD else "FAIL"
                verdict_flag = "[+]" if verdict_correct else "[!]"
                lines = [f"  [{case['id']}] {case['description']}... {status} ({composite:.1f}/5.0) verdict {verdict_flag}"]
                if verbose:
                    lines.append(
                        f"     Traceability: {score.get('traceability'):.1f}  "
                        f"Accuracy: {score.get('accuracy'):.1f}  "
                        f"Actionability: {score.get('actionability'):.1f}"
                    )
                    if score.get("missed_findings"):
                        lines.append(f"     Missed: {score['missed_findings']}")
                    if score.get("hallucinated_findings"):
                        lines.append(f"     Hallucinated: {score['hallucinated_findings']}")

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
                lines = [f"  [{case['id']}] {case['description']}... ERROR ({e})"]

            case_results[idx] = result
            # Print immediately as each case finishes so the terminal isn't silent
            async with print_lock:
                print("\n".join(lines), flush=True)

    # Launch all cases concurrently (bounded by semaphore)
    await asyncio.gather(*[_run_case(i, c) for i, c in enumerate(golden_cases)])

    # Accumulate totals in original case order
    for result in case_results:
        results.append(result)
        total_composite += result.get("composite_score", 0.0)

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

    # Append to regression log
    _append_regression_log(summary)

    print(f"\n{'='*60}")
    print(f"  Results: {cases_passed}/{len(results)} passed")
    print(f"  Average composite score: {avg_composite:.2f}/5.0")
    status = "PASSED" if passed_threshold else "FAILED"
    print(f"  Threshold ({_REGRESSION_THRESHOLD}/5.0): {status}")
    print(f"  Logged to: {_REGRESSION_LOG}")
    print(f"{'='*60}\n")

    if not passed_threshold:
        print("  [!] Regression threshold not met. Review failed cases and")
        print("      revise skills/prompts in Layer 1 before deployment.\n")

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
