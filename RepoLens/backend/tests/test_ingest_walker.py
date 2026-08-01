import shutil
import subprocess
from pathlib import Path

from app.ingest import walker

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_walk_respects_gitignore_and_filters_extensions() -> None:
    files = walker.walk(FIXTURE)
    rel_paths = {f.path for f in files}

    assert "pkg/scratch_ignored.py" not in rel_paths
    assert "pkg/models.py" in rel_paths
    assert "pkg/utils.py" in rel_paths
    assert "pkg/__init__.py" in rel_paths
    assert "README.md" in rel_paths
    assert ".gitignore" not in rel_paths


def test_walk_git_tracked_path_also_respects_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)

    files = walker.walk(repo)
    rel_paths = {f.path for f in files}
    assert "pkg/scratch_ignored.py" not in rel_paths
    assert "pkg/models.py" in rel_paths
