"""
Sentinel Eval Runner.

Runs the full eval corpus and produces the results table.
This is the quantified proof that Sentinel works.

Metrics:
- Target detection rate: vulnerable targets caught (verdict != pass) /
  total vulnerable targets. This is target-level, not per-seeded-vuln:
  a target counts as detected if ANY of its seeded vulns is caught.
- Hallucinated-finding rate: findings on clean controls / clean controls
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sentinel.pipeline import run_sentinel


# Ground truth: which targets have seeded vulnerabilities
EVAL_CORPUS = [
    {
        "target": "targets/t1_injection",
        "label": "T1 — Injection",
        "expected_verdict": "fail",
        "seeded_vulns": ["eval() injection", "subprocess shell=True"],
        "is_clean": False,
    },
    {
        "target": "targets/t2_privilege",
        "label": "T2 — Privilege Leak",
        "expected_verdict": "fail",
        "seeded_vulns": ["hardcoded API key", "hardcoded password"],
        "is_clean": False,
    },
    {
        "target": "targets/t3_secrets",
        "label": "T3 — Secret Leak",
        "expected_verdict": "fail",
        "seeded_vulns": ["hardcoded credentials"],
        "is_clean": False,
    },
    {
        "target": "targets/t4_sqli",
        "label": "T4 — SQL Injection",
        "expected_verdict": "fail",
        "seeded_vulns": ["SQL injection"],
        "is_clean": False,
    },
    {
        "target": "targets/t5_deserial",
        "label": "T5 — Unsafe Deserial",
        "expected_verdict": "fail",
        "seeded_vulns": ["pickle deserialization", "subprocess shell=True"],
        "is_clean": False,
    },
    {
        "target": "targets/c1_clean",
        "label": "C1 — Clean Control",
        "expected_verdict": "pass",
        "seeded_vulns": [],
        "is_clean": True,
    },
    {
        "target": "targets/c2_clean",
        "label": "C2 — Clean Control",
        "expected_verdict": "pass",
        "seeded_vulns": [],
        "is_clean": True,
    },
]


def run_eval() -> dict:
    """
    Run the full eval corpus and return metrics.
    """
    print("\n" + "="*70)
    print("SENTINEL EVAL — Full Corpus Run")
    print("="*70)

    results = []
    total_vulnerable_targets = 0
    detected_targets = 0
    false_positives_on_clean = 0

    for item in EVAL_CORPUS:
        target = item["target"]
        label = item["label"]
        is_clean = item["is_clean"]
        expected = item["expected_verdict"]

        print(f"\n[Eval] Running: {label} ({target})")

        try:
            attestation = run_sentinel(target, verbose=False)
            actual_verdict = attestation.verdict
            findings_count = len(attestation.findings)
            correct = (
                (is_clean and actual_verdict == "pass") or
                (not is_clean and actual_verdict != "pass")
            )

            if not is_clean:
                total_vulnerable_targets += 1
                if actual_verdict != "pass":
                    detected_targets += 1

            if is_clean and findings_count > 0:
                false_positives_on_clean += findings_count

            result = {
                "label": label,
                "target": target,
                "expected": expected,
                "actual": actual_verdict,
                "correct": correct,
                "findings": findings_count,
                "is_clean": is_clean,
            }
            results.append(result)

            status = "✅" if correct else "❌"
            print(f"  {status} {label}: {actual_verdict.upper()} "
                  f"({findings_count} findings)")

        except Exception as e:
            print(f"  ❌ {label}: ERROR — {e}")
            results.append({
                "label": label,
                "target": target,
                "expected": expected,
                "actual": "error",
                "correct": False,
                "findings": 0,
                "is_clean": is_clean,
            })

    # Calculate metrics
    clean_control_count = sum(1 for item in EVAL_CORPUS if item["is_clean"])
    target_detection_rate = (
        detected_targets / total_vulnerable_targets
        if total_vulnerable_targets > 0 else 0
    )
    hallucination_rate = (
        false_positives_on_clean / clean_control_count
        if clean_control_count > 0 else 0
    )

    print("\n" + "="*70)
    print("SENTINEL EVAL RESULTS")
    print("="*70)
    print(f"\n{'Target':<25} {'Expected':<15} {'Actual':<20} {'✓'}")
    print("-"*65)
    for r in results:
        status = "✅" if r["correct"] else "❌"
        print(f"{r['label']:<25} {r['expected']:<15} "
              f"{r['actual']:<20} {status}")

    print("\n" + "-"*70)
    print("METRICS:")
    print(f"  Target detection rate:     {target_detection_rate:.0%} "
          f"({detected_targets}/{total_vulnerable_targets} vulnerable targets detected)")
    print(f"  False positives on clean:  {false_positives_on_clean} findings "
          f"({hallucination_rate:.1f} avg per clean target)")
    print(f"  Hallucinated-finding rate: "
          f"{'0%' if false_positives_on_clean == 0 else f'{hallucination_rate:.0%}'}")
    print("="*70 + "\n")

    return {
        "results": results,
        "metrics": {
            "target_detection_rate": target_detection_rate,
            "detected_targets": detected_targets,
            "total_vulnerable_targets": total_vulnerable_targets,
            "false_positives_on_clean": false_positives_on_clean,
            "hallucination_rate": hallucination_rate,
        },
    }


if __name__ == "__main__":
    run_eval()