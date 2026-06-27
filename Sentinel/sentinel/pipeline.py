"""
Sentinel Pipeline — Full end-to-end security review.
"""
from sentinel.agents.evidence_agent import collect_evidence
from sentinel.agents.injection_auditor import audit_for_injection
from sentinel.agents.adjudicator import adjudicate
from sentinel.skills.skill_loader import select_skills_for_target, load_skill_frontmatter
from sentinel.models.schemas import Attestation


def run_sentinel(target_path: str, verbose: bool = True) -> Attestation:
    """
    Run a complete Sentinel security review on a target.
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

    # Stage 3: Run specialist auditors
    if verbose:
        print("\n[Stage 3] Running specialist auditors...")
    all_candidates = []
    if "prompt-injection-defense" in selected_skills:
        injection_candidates = audit_for_injection(evidence_list)
        if verbose:
            print(f"  → InjectionAuditor: {len(injection_candidates)} candidates")
        all_candidates.extend(injection_candidates)

    # Stage 4: Adjudicate
    if verbose:
        print(f"\n[Stage 4] Adjudicating {len(all_candidates)} candidates...")
    evidence_dicts = [ev.model_dump() for ev in evidence_list]
    attestation = adjudicate(all_candidates, evidence_dicts, target_path)

    # Stage 5: Summary
    if verbose:
        print(f"\n[Stage 5] Review complete.")
        print(f"  Verdict:  {attestation.verdict.upper()}")
        print(f"  Findings: {len(attestation.findings)}")
        print(f"  Ref:      {attestation.audit_ref}")
        print("="*60 + "\n")

    return attestation