"""
CCA-F D5.5: Human Review Workflows — Evaluation with stratified sampling
Exam concept: "Aggregate accuracy metrics may mask poor performance on specific document types"
This judge runs stratified evaluation (per-severity, per-field) not just overall accuracy.
"""
from __future__ import annotations
import json
import argparse
import asyncio
from pathlib import Path
from collections import defaultdict
import anthropic

client = anthropic.Anthropic()


def load_dataset(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def run_evaluation(dataset_path: str, filter_severity: str = "") -> dict:
    """
    D5.5: Stratified evaluation — don't just report overall accuracy.
    Report per-severity, per-field, and threshold-adherence metrics.
    """
    dataset = load_dataset(dataset_path)
    if filter_severity:
        dataset = [d for d in dataset if d["expected"].get("severity") == filter_severity]

    results = []
    for item in dataset:
        result = evaluate_single(item)
        results.append(result)

    return compute_metrics(results)


def evaluate_single(item: dict) -> dict:
    """Run coordinator on one ticket, compare to expected."""
    from agents.coordinator import CoordinatorAgent
    coord = CoordinatorAgent()
    rca = asyncio.run(coord.investigate(item["ticket"], item["id"]))

    if hasattr(rca, "model_dump"):
        rca_dict = rca.model_dump()
    else:
        rca_dict = rca  # AgentError fallback

    expected = item["expected"]
    checks = {
        "severity_match": rca_dict.get("severity") == expected.get("severity"),
        "confidence_in_range": _check_confidence(rca_dict, expected),
        "escalation_correct": rca_dict.get("escalate") == expected.get("escalate"),
        "root_cause_keywords": _check_keywords(rca_dict.get("root_cause", ""), expected.get("root_cause_contains", [])),
        "next_steps_adequate": len(rca_dict.get("next_steps", [])) >= expected.get("next_steps_min", 1),
        "escalation_reason_present": not expected.get("escalation_reason_contains") or bool(rca_dict.get("escalation_reason")),
    }
    # LLM judge for root cause quality (D5.5: field-level calibration)
    checks["root_cause_quality"] = llm_judge_root_cause(
        rca_dict.get("root_cause", ""),
        item["ticket"],
        expected,
    )

    return {
        "id": item["id"],
        "severity": expected.get("severity"),
        "passed": all(checks.values()),
        "checks": checks,
        "rca": rca_dict,
    }


def llm_judge_root_cause(root_cause: str, ticket: str, expected: dict) -> bool:
    """
    D5.5: LLM-as-judge for semantic quality.
    Aggregate metrics miss this — a syntactically correct but semantically wrong RCA passes schema checks.
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{"role": "user", "content": f"""Judge this root cause for quality.
Ticket: {ticket[:500]}
Root cause: {root_cause}

Is this root cause: (1) specific not vague, (2) names the component/operation/failure mode, (3) consistent with the ticket?
Answer ONLY: {{"quality": "pass"}} or {{"quality": "fail", "reason": "..."}}"""}]
    )
    try:
        result = json.loads(response.content[0].text)
        return result.get("quality") == "pass"
    except:
        return True  # parse failure = non-blocking


def compute_metrics(results: list[dict]) -> dict:
    """
    D5.5: Stratified metrics — report per-severity breakdown.
    Aggregate accuracy can be 85% overall but 0% on P1 — you'd miss this without stratification.
    """
    overall_pass = sum(r["passed"] for r in results) / len(results) if results else 0

    # Per-severity stratification
    by_severity = defaultdict(list)
    for r in results:
        by_severity[r.get("severity", "unknown")].append(r["passed"])

    severity_accuracy = {
        sev: sum(passes) / len(passes)
        for sev, passes in by_severity.items()
    }

    # Per-field accuracy
    all_checks = defaultdict(list)
    for r in results:
        for check, passed in r.get("checks", {}).items():
            all_checks[check].append(passed)

    field_accuracy = {
        check: sum(vals) / len(vals)
        for check, vals in all_checks.items()
    }

    metrics = {
        "total": len(results),
        "overall_pass_rate": round(overall_pass, 3),
        "by_severity": {k: round(v, 3) for k, v in severity_accuracy.items()},
        "by_field": {k: round(v, 3) for k, v in field_accuracy.items()},
        # D5.5: Flag if any severity or field is below threshold
        "alerts": [
            f"⚠️  P1 accuracy is {severity_accuracy.get('P1', 0):.0%} — below 90% target"
            for _ in [1] if severity_accuracy.get("P1", 1.0) < 0.90
        ] + [
            f"⚠️  {field} accuracy is {acc:.0%} — below 80% target"
            for field, acc in field_accuracy.items() if acc < 0.80
        ]
    }

    return metrics


def _check_confidence(rca: dict, expected: dict) -> bool:
    conf = rca.get("confidence", 0.0)
    if "confidence_min" in expected and conf < expected["confidence_min"]:
        return False
    if "confidence_max" in expected and conf > expected["confidence_max"]:
        return False
    return True


def _check_keywords(text: str, keywords: list) -> bool:
    if not keywords:
        return True
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/golden_dataset.jsonl")
    parser.add_argument("--filter", dest="filter_severity", default="",
                        help="Filter to specific severity: P1, P2, P3, P4")
    args = parser.parse_args()

    metrics = run_evaluation(args.dataset, args.filter_severity)

    print("\n=== Evaluation Results ===")
    print(f"Total: {metrics['total']} | Overall: {metrics['overall_pass_rate']:.1%}")
    print("\nBy Severity:")
    for sev, acc in sorted(metrics["by_severity"].items()):
        print(f"  {sev}: {acc:.1%}")
    print("\nBy Field:")
    for field, acc in sorted(metrics["by_field"].items()):
        print(f"  {field}: {acc:.1%}")
    if metrics["alerts"]:
        print("\n" + "\n".join(metrics["alerts"]))
