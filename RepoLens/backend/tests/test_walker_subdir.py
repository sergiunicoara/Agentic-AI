import subprocess
from pathlib import Path

from app.ingest import walker


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)


def test_walk_scopes_to_subdir_via_git(tmp_path: Path) -> None:
    (tmp_path / "pkg_a").mkdir()
    (tmp_path / "pkg_a" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg_b").mkdir()
    (tmp_path / "pkg_b" / "b.py").write_text("y = 2\n")
    _init_git_repo(tmp_path)

    files = walker.walk(tmp_path, subdir="pkg_a")

    assert {f.path for f in files} == {"pkg_a/a.py"}


def test_walk_subdir_respects_root_gitignore(tmp_path: Path) -> None:
    (tmp_path / "pkg_a").mkdir()
    (tmp_path / "pkg_a" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg_a" / "ignored.py").write_text("z = 3\n")
    (tmp_path / ".gitignore").write_text("pkg_a/ignored.py\n")
    _init_git_repo(tmp_path)

    files = walker.walk(tmp_path, subdir="pkg_a")

    assert {f.path for f in files} == {"pkg_a/a.py"}
