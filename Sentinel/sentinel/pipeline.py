"""
Sentinel Pipeline — Full end-to-end security review.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentinel.agents.evidence_agent import collect_evidence
from sentinel.agents.injection_auditor import audit_for_injection
from sentinel.agents.privilege_auditor import audit_for_privilege
from sentinel.agents.supply_chain_auditor import audit_for_supply_chain
from sentinel.agents.redteam_auditor import audit_for_redteam
from sentinel.agents.llm_auditor import audit_with_llm
from sentinel.agents.adjudicator import adjudicate
from sentinel.skills.skill_loader import select_skills_for_target, load_skill_frontmatter
from sentinel.models.schemas import Attestation
# Note: utf-8 stdout/stderr reconfiguration for console report glyphs is
# done centrally in sentinel/__init__.py so it applies to every entry point.


def run_sentinel(
    target_path: str,
    verbose: bool = True,
    include_red_team: bool = False,
    include_live_red_team: bool = False,
    include_llm_auditor: bool = False,
    return_red_team: bool = False,
    sarif_output: str | None = None,
) -> Attestation:
    """
    Run a complete Sentinel security review on a target.

    Args:
        return_red_team: If True, return (Attestation, red_team_summary)
            instead of just the Attestation. red_team_summary is None
            unless include_red_team is also True. Use this instead of
            calling run_red_team again to avoid scanning the target twice.
        include_live_red_team: If True, actually execute red team payloads
            against the target's real functions in a sandboxed subprocess
            (see sentinel/redteam/live_runner.py for the safety model),
            instead of only checking for static surfaces. Off by default —
            this runs real code paths and is meant for the bundled,
            trusted target corpus, not arbitrary third-party code.
        include_llm_auditor: If True, also run the LLM-driven auditor
            (requires Vertex AI credentials). This is the only auditor
            whose candidate findings can be hallucinated — the Adjudicator
            gate is what keeps unsupported ones out. Off by default so the
            deterministic eval/test suite never depends on live API access.
        sarif_output: If set, write the attestation as a SARIF 2.1.0 log
            to this path — for CI security-gate integration.
    """
    if verbose:
        print("\n" + "="*60)
        print("SENTINEL — Agent Security Review")
        print("="*60)
        print(f"Target: {target_path}")

    # Stage 1: Profile target and select skills
    if verbose:
        print("\n[Stage 1] Profiling target and selecting skills...")
    selected_skills = select_skills_for_target(target_path)
    if verbose:
        for skill_name in selected_skills:
            fm = load_skill_frontmatter(skill_name)
            print(f"  → Loaded skill: {fm.get('name', skill_name)}")

    # Stage 2: Collect deterministic evidence
    if verbose:
        print("\n[Stage 2] Collecting deterministic evidence...")
    evidence_list = collect_evidence(target_path)

    # Stage 2b: Red team (optional — static surface match, and/or live execution)
    red_team_summary = None
    live_red_team_summary = None
    from sentinel.models.schemas import Evidence

    if include_red_team:
        if verbose:
            print("\n[Stage 2b] Running red team assessment...")
        from sentinel.redteam.runner import run_red_team
        red_team_summary = run_red_team(target_path)
        for ev_dict in red_team_summary.get("trajectory_evidence", []):
            evidence_list.append(Evidence(**ev_dict))

    if include_live_red_team:
        if verbose:
            print("\n[Stage 2c] Running LIVE red team assessment (sandboxed execution)...")
        from sentinel.redteam.live_runner import run_live_red_team
        live_red_team_summary = run_live_red_team(target_path)
        for ev_dict in live_red_team_summary.get("trajectory_evidence", []):
            evidence_list.append(Evidence(**ev_dict))

    # Stage 3: Run specialist auditors
    if verbose:
        print("\n[Stage 3] Running specialist auditors...")
    all_candidates = []

    if "prompt-injection-defense" in selected_skills:
        candidates = audit_for_injection(evidence_list)
        if verbose:
            print(f"  → InjectionAuditor: {len(candidates)} candidates")
        all_candidates.extend(candidates)

    if "confused-deputy-iam" in selected_skills:
        candidates = audit_for_privilege(evidence_list)
        if verbose:
            print(f"  → PrivilegeAuditor: {len(candidates)} candidates")
        all_candidates.extend(candidates)

    if "supply-chain-integrity" in selected_skills:
        candidates = audit_for_supply_chain(evidence_list)
        if verbose:
            print(f"  → SupplyChainAuditor: {len(candidates)} candidates")
        all_candidates.extend(candidates)

    if include_red_team or include_live_red_team:
        candidates = audit_for_redteam(evidence_list)
        if verbose:
            print(f"  → RedTeamAuditor: {len(candidates)} candidates")
        all_candidates.extend(candidates)

    if include_llm_auditor:
        candidates = audit_with_llm(evidence_list, target_path)
        if verbose:
            print(f"  → LLMAuditor: {len(candidates)} candidates")
        all_candidates.extend(candidates)

    # Stage 4: Adjudicate
    if verbose:
        print(f"\n[Stage 4] Adjudicating {len(all_candidates)} candidates...")
    evidence_dicts = [ev.model_dump() for ev in evidence_list]
    attestation = adjudicate(all_candidates, evidence_dicts, target_path)

    if sarif_output:
        from sentinel.eval.sarif import write_sarif
        write_sarif(attestation, sarif_output)
        if verbose:
            print(f"\n[SARIF] Report written to {sarif_output}")

    # Stage 5: Summary
    if verbose:
        print("\n[Stage 5] Review complete.")
        print(f"  Verdict:  {attestation.verdict.upper()}")
        print(f"  Findings: {len(attestation.findings)}")
        print(f"  Ref:      {attestation.audit_ref}")
        if red_team_summary:
            rate = red_team_summary["injection_success_rate"]
            print(f"  Red Team: {rate:.0%} injection success rate")
        if live_red_team_summary:
            n, total = live_red_team_summary["live_confirmed"], live_red_team_summary["total_invocations"]
            print(f"  Live Red Team: {n}/{total} invocations live-confirmed")
        print("="*60 + "\n")

    if return_red_team:
        return attestation, red_team_summary
    return attestation


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a Sentinel security review (CI-friendly CLI)."
    )
    parser.add_argument("target_path", help="Path to the agent/repo to review")
    parser.add_argument("--red-team", action="store_true",
                         help="Include adversarial red team assessment (static surface match)")
    parser.add_argument("--live-red-team", action="store_true",
                         help="Actually execute red team payloads in a sandboxed subprocess "
                              "(see sentinel/redteam/live_runner.py docstring for the safety model)")
    parser.add_argument("--llm-auditor", action="store_true",
                         help="Include the LLM-driven auditor (requires Vertex AI credentials)")
    parser.add_argument("--sarif", metavar="PATH",
                         help="Write a SARIF 2.1.0 report to PATH")
    parser.add_argument("--fail-on", choices=["fail", "pass_with_findings"],
                         default="fail",
                         help="Exit non-zero if the verdict is at least this severe")
    args = parser.parse_args()

    result = run_sentinel(
        args.target_path,
        verbose=True,
        include_red_team=args.red_team,
        include_live_red_team=args.live_red_team,
        include_llm_auditor=args.llm_auditor,
        sarif_output=args.sarif,
    )

    severity_rank = {"pass": 0, "pass_with_findings": 1, "fail": 2}
    if severity_rank[result.verdict] >= severity_rank[args.fail_on]:
        sys.exit(1)