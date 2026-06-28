"""
Scope Agent — profiles the target and selects which Skills to load.
Real ADK LlmAgent that reasons about target capabilities.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from sentinel.skills.skill_loader import select_skills_for_target, load_skill_frontmatter


def profile_target(target_path: str) -> dict:
    """
    Profile a target agent and select relevant security skills.
    Returns selected skill names and their descriptions.

    Args:
        target_path: Path to the target agent or repository
    """
    selected = select_skills_for_target(target_path)
    skill_details = []
    for name in selected:
        fm = load_skill_frontmatter(name)
        skill_details.append({
            "name": name,
            "description": fm.get("description", ""),
            "pillar": fm.get("pillar", "?"),
            "triggers": fm.get("triggers", ""),
        })
    return {
        "target": target_path,
        "selected_skills": selected,
        "skill_details": skill_details,
        "skill_count": len(selected),
    }


scope_agent = Agent(
    name="scope_agent",
    model="gemini-2.5-flash",
    instruction="""You are the Scope Agent — the first stage of Sentinel's
security review pipeline.

Your job is to profile a target agent or repository and decide which
security skill domains are relevant for the review.

Call profile_target with the target path. Then explain:
1. Which skills were selected and why
2. What security domains are most relevant given the target's code patterns
3. What the review will focus on

Be concise — your output is consumed by downstream agents.""",
    tools=[profile_target],
)
