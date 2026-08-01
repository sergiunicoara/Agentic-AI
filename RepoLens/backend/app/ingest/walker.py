import subprocess
import tempfile
from pathlib import Path

from pathspec import GitIgnoreSpec

from app.ingest.models import SourceFile

DEFAULT_IGNORE_DIRS = {".git", "__pycache__", ".venv", "node_modules", "dist", "build"}
SUPPORTED_EXTENSIONS = {".py": "python", ".md": "markdown"}


def resolve_source(source: str) -> tuple[Path, bool]:
    """Return (local_path, is_temp_clone). Clones if `source` looks like a git URL."""
    if source.startswith(("http://", "https://", "git@")):
        tmpdir = Path(tempfile.mkdtemp(prefix="codex-ingest-"))
        subprocess.run(
            ["git", "clone", "--depth", "1", source, str(tmpdir)],
            check=True,
            capture_output=True,
        )
        return tmpdir, True
    return Path(source).resolve(), False


def _git_tracked_files(repo_path: Path, subdir: str | None) -> list[str] | None:
    """Git-tracked + untracked-but-not-ignored files, or None if not a git repo.

    When `subdir` is given, scopes the listing via git's own pathspec (`-- <subdir>`)
    so `.gitignore` is still resolved correctly from the real repo root.
    """
    if not (repo_path / ".git").exists():
        return None
    cmd = ["git", "-C", str(repo_path), "ls-files", "--cached", "--others", "--exclude-standard"]
    if subdir:
        cmd += ["--", subdir]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line]


def _pathspec_walk(repo_path: Path, subdir: str | None) -> list[str]:
    """Fallback for non-git local directories: honor a root .gitignore + default ignores."""
    gitignore_path = repo_path / ".gitignore"
    patterns = (
        gitignore_path.read_text(encoding="utf-8").splitlines() if gitignore_path.exists() else []
    )
    spec = GitIgnoreSpec.from_lines(patterns)

    walk_root = (repo_path / subdir) if subdir else repo_path
    files: list[str] = []
    for path in walk_root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(repo_path)
        if any(part in DEFAULT_IGNORE_DIRS for part in rel.parts):
            continue
        rel_posix = rel.as_posix()
        if spec.match_file(rel_posix):
            continue
        files.append(rel_posix)
    return files


def walk(repo_path: Path, subdir: str | None = None) -> list[SourceFile]:
    """List ingestible (.py/.md) files under `repo_path`, respecting .gitignore.

    `subdir`, if given, scopes ingestion to that subdirectory (e.g. a package dir
    within a larger repo) while still resolving `.gitignore` from the repo root.
    """
    tracked = _git_tracked_files(repo_path, subdir)
    rel_paths = tracked if tracked is not None else _pathspec_walk(repo_path, subdir)

    files: list[SourceFile] = []
    for rel_path in rel_paths:
        language = SUPPORTED_EXTENSIONS.get(Path(rel_path).suffix)
        if language is None:
            continue
        abs_path = repo_path / rel_path
        if not abs_path.is_file():
            continue
        files.append(SourceFile(path=rel_path, abs_path=abs_path, language=language))
    return files
