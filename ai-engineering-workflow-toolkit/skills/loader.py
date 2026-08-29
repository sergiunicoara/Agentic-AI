"""
Layer 1: Skill Loader
Selects and loads the appropriate versioned skills for a given diff.
"""
import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def load_skills_for_diff(diff: str, repo_root: Path | None = None) -> list[dict]:
    """
    Inspect the diff and return a list of loaded skill dicts:
    [{"id": ..., "version": ..., "content": ...}, ...]
    """
    root = repo_root or _REPO_ROOT
    registry_path = root / "skills" / "registry.json"

    with open(registry_path) as f:
        registry = json.load(f)

    extensions = _extract_extensions(diff)
    change_type = _detect_change_type(diff)
    diff_lower = diff.lower()

    loaded = []
    for skill in registry["skills"]:
        criteria = skill["applies_to"]

        ext_match = any(ext in extensions for ext in criteria["extensions"])
        pattern_match = (
            not criteria["patterns"]
            or any(p in diff_lower for p in criteria["patterns"])
        )
        type_match = change_type in criteria["change_types"]

        if ext_match and type_match and pattern_match:
            skill_path = root / skill["path"]
            content = skill_path.read_text(encoding="utf-8")
            loaded.append({
                "id": skill["id"],
                "version": skill["version"],
                "content": content,
            })

    # Always load at least style and architecture for any code diff
    loaded_ids = {s["id"] for s in loaded}
    for skill in registry["skills"]:
        if skill["id"] not in loaded_ids and skill["id"] in (
            "style_review_v1", "architecture_review_v1"
        ):
            skill_path = root / skill["path"]
            content = skill_path.read_text(encoding="utf-8")
            loaded.append({
                "id": skill["id"],
                "version": skill["version"],
                "content": content,
            })

    return loaded


def _extract_extensions(diff: str) -> set[str]:
    """Extract unique file extensions from diff headers."""
    extensions = set()
    for match in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.MULTILINE):
        path = match.group(1)
        ext = Path(path).suffix.lower()
        if ext:
            extensions.add(ext)
    return extensions


def _detect_change_type(diff: str) -> str:
    """Return 'add' if only additions, 'delete' if only deletions, else 'modify'."""
    has_add = bool(re.search(r"^\+[^+]", diff, re.MULTILINE))
    has_del = bool(re.search(r"^-[^-]", diff, re.MULTILINE))
    if has_add and not has_del:
        return "add"
    if has_del and not has_add:
        return "delete"
    return "modify"
