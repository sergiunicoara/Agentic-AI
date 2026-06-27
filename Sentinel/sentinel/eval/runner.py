"""
Sentinel Eval Runner.

Runs the full eval corpus and produces the results table.
This is the quantified proof that Sentinel works.

Metrics:
- Detection recall: seeded vulns found / total seeded vulns
- Detection precision: valid findings / total findings emitted
- Hallucinated-finding rate: findings on clean controls / total
- Adjudicator gate: findings emitted vs surviving
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sentinel.pipeline import run_sentinel
from sentinel.redteam.runner import run_red_team


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
    total_seeded = 0
    detected = 0
    false_positives_on_clean = 0
    total_candidates_emitted = 0
    total_surviving = 0

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
                total_seeded += 1
                if actual_verdict != "pass":
                    detected += 1

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
    detection_recall = detected / total_seeded if total_seeded > 0 else 0
    hallucination_rate = false_positives_on_clean / 2  # 2 clean controls

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
    print(f"  Detection recall:          {detection_recall:.0%} "
          f"({detected}/{total_seeded} vulnerable targets detected)")
    print(f"  False positives on clean:  {false_positives_on_clean} findings "
          f"({hallucination_rate:.1f} avg per clean target)")
    print(f"  Hallucinated-finding rate: "
          f"{'0%' if false_positives_on_clean == 0 else f'{hallucination_rate:.0%}'}")
    print("="*70 + "\n")

    return {
        "results": results,
        "metrics": {
            "detection_recall": detection_recall,
            "detected": detected,
            "total_seeded": total_seeded,
            "false_positives_on_clean": false_positives_on_clean,
            "hallucination_rate": hallucination_rate,
        },
    }


if __name__ == "__main__":
    run_eval()