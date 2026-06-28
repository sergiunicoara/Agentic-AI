"""
LLM Gate Report — quantifies the Adjudicator's evidence gate against the
LLM auditor specifically, across the full eval corpus.

The other auditors (Injection, Privilege, SupplyChain, RedTeam) are
deterministic lookup tables: they cannot propose an unsupported finding,
so the gate is defense-in-depth for them with nothing to measure. The
LLM auditor is the one specialist that reasons freely and CAN hallucinate
— this report measures, target by target, how many candidates it
proposed and how many survived the Adjudicator's evidence check.

Requires Vertex AI credentials (GOOGLE_GENAI_USE_VERTEXAI, etc. in .env).
If they aren't configured, every row degrades to "0 proposed" rather than
erroring — sentinel.agents.llm_auditor.audit_with_llm already fails safe.
For an offline, deterministic proof that the gate enforces this even when
the LLM does hallucinate, see tests/test_llm_auditor.py — this report
shows what happens with a real model; that test shows the gate cannot be
bypassed even when it does.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sentinel.agents.evidence_agent import collect_evidence
from sentinel.agents.llm_auditor import audit_with_llm
from sentinel.agents.adjudicator import adjudicate
from sentinel.eval.runner import EVAL_CORPUS


def run_llm_gate_report() -> dict:
    """
    For each corpus target: collect evidence, ask the LLM auditor for
    candidates, adjudicate ONLY those candidates (isolated from the
    deterministic auditors so this measures the LLM auditor specifically),
    and record proposed vs. survived counts plus any drop reasons.
    """
    print("\n" + "=" * 70)
    print("SENTINEL LLM GATE REPORT — Adjudicator vs. the LLM Auditor")
    print("=" * 70)

    rows = []
    total_proposed = 0
    total_survived = 0
    total_unsupported = 0  # proposed but missing/fake evidence_ids

    for item in EVAL_CORPUS:
        target = item["target"]
        label = item["label"]

        evidence_list = collect_evidence(target)
        candidates = audit_with_llm(evidence_list, target)

        evidence_dicts = [e.model_dump() for e in evidence_list]
        attestation = adjudicate(candidates, evidence_dicts, target)

        proposed = len(candidates)
        survived = len(attestation.findings)
        unsupported = proposed - survived

        total_proposed += proposed
        total_survived += survived
        total_unsupported += unsupported

        rows.append({
            "label": label,
            "target": target,
            "proposed": proposed,
            "survived": survived,
            "unsupported": unsupported,
        })

        print(f"\n[LLM Gate] {label}: proposed={proposed} survived={survived} "
              f"unsupported={unsupported}")

    print("\n" + "-" * 70)
    print(f"{'Target':<30} {'Proposed':>10} {'Survived':>10} {'Unsupported':>12}")
    print("-" * 70)
    for r in rows:
        print(f"{r['label']:<30} {r['proposed']:>10} {r['survived']:>10} "
              f"{r['unsupported']:>12}")
    print("-" * 70)
    print(f"{'TOTAL':<30} {total_proposed:>10} {total_survived:>10} "
          f"{total_unsupported:>12}")

    survival_rate = total_survived / total_proposed if total_proposed > 0 else None
    print("\nMETRICS:")
    if total_proposed == 0:
        print("  No candidates proposed — either every target produced no "
              "findings, or Vertex AI credentials are not configured "
              "(audit_with_llm fails safe to []). See module docstring.")
    else:
        print(f"  Evidence-backed survival rate: {survival_rate:.0%} "
              f"({total_survived}/{total_proposed})")
        print(f"  Unsupported candidates dropped: {total_unsupported}")
    print("=" * 70 + "\n")

    return {
        "rows": rows,
        "total_proposed": total_proposed,
        "total_survived": total_survived,
        "total_unsupported": total_unsupported,
        "survival_rate": survival_rate,
    }


if __name__ == "__main__":
    run_llm_gate_report()
