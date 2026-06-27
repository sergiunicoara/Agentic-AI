"""
Skill Loader — loads SKILL.md files as structured domain context.
Implements progressive disclosure: front-matter loaded always,
full content loaded only when the skill is activated for a scan.
"""
from pathlib import Path
import re

SKILLS_DIR = Path(__file__).parent


def _contains_any_token(code: str, tokens: list[str]) -> bool:
    """
    Word-boundary match for trigger tokens, so e.g. "token" doesn't
    match inside "tokenizer" or "AUTH" inside "AUTHOR".
    Tokens containing non-word characters (like "shell=True") fall back
    to a plain substring check since \\b doesn't apply to them.
    """
    for t in tokens:
        if re.search(r"\w", t) and re.fullmatch(r"[\w]+", t):
            if re.search(rf"\b{re.escape(t)}\b", code, re.IGNORECASE):
                return True
        elif t in code:
            return True
    return False

AVAILABLE_SKILLS = [
    "prompt-injection-defense",
    "confused-deputy-iam",
    "supply-chain-integrity",
]


def load_skill_frontmatter(skill_name: str) -> dict:
    """
    Load only the front-matter (name, description, triggers, pillar).
    Used by ScopeAgent to decide which skills to activate.
    """
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        return {}

    content = skill_path.read_text(encoding="utf-8")
    frontmatter = {}

    match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()

    return frontmatter


def load_skill_full(skill_name: str) -> str:
    """
    Load the full SKILL.md content.
    Used by specialist auditor agents as their domain instruction.
    """
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        return f"Skill '{skill_name}' not found."
    return skill_path.read_text(encoding="utf-8")


def select_skills_for_target(target_path: str) -> list[str]:
    """
    Profile a target and return relevant skill names.
    Checks for triggers: eval/exec → injection skill,
    requirements.txt → supply chain skill, etc.
    """
    target = Path(target_path)
    selected = []
    
    # Read all Python files in target
    code = ""
    for py_file in target.rglob("*.py"):
        try:
            code += py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    # Check for injection triggers
    injection_triggers = ["eval(", "exec(", "subprocess", "shell=True",
                         "web_fetch", "requests.get", "urllib"]
    if _contains_any_token(code, injection_triggers):
        selected.append("prompt-injection-defense")

    # Check for IAM/credential triggers
    iam_triggers = ["api_key", "token", "secret", "password",
                   "credential", "AUTH", "Bearer"]
    if _contains_any_token(code, iam_triggers):
        selected.append("confused-deputy-iam")

    # Check for supply chain triggers
    req_file = target / "requirements.txt"
    pyproject = target / "pyproject.toml"
    if req_file.exists() or pyproject.exists():
        selected.append("supply-chain-integrity")

    # Default: always include injection defense
    if not selected:
        selected.append("prompt-injection-defense")

    return selected