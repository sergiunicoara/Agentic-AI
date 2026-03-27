"""
Layer 3a: MCP Server — Deterministic Tools

Exposes three deterministic tool functions:
  - run_linter          → ruff check
  - run_type_checker    → mypy
  - run_security_scanner → bandit

Each function:
  1. Extracts changed file paths from the diff
  2. Runs the tool on those files (if they exist on disk)
  3. Returns structured JSON with file, line, severity, rule, message

Also registers these as a proper FastMCP server so Claude Code can call them
via the Model Context Protocol when started with `python main.py serve`.
"""
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

try:
    from fastmcp import FastMCP
    _mcp = FastMCP("ai-engineering-workflow-toolkit")
except ImportError:
    _mcp = None  # FastMCP optional; direct function calls always work

from observability.tracer import get_tracer

tracer = get_tracer("mcp_server")


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_changed_files(diff: str, repo_root: Path) -> list[Path]:
    """Return absolute paths of files modified in the diff that exist on disk."""
    paths = []
    for match in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.MULTILINE):
        rel = match.group(1).strip()
        abs_path = repo_root / rel
        if abs_path.exists() and abs_path.is_file():
            paths.append(abs_path)
    return paths


def _write_diff_as_temp_files(diff: str) -> tuple[Path, list[Path]]:
    """
    Write added lines from the diff into temp files so tools can analyse them
    even when the files don't exist on disk (e.g. CI/review-only mode).
    Returns (temp_dir, [file_paths]).
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="aiwt_"))
    files: list[Path] = []
    current_file: Path | None = None
    lines: list[str] = []

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            if current_file and lines:
                current_file.parent.mkdir(parents=True, exist_ok=True)
                current_file.write_text("\n".join(lines), encoding="utf-8")
                files.append(current_file)
            rel = line[6:].strip()
            current_file = tmp_dir / rel
            lines = []
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])

    if current_file and lines:
        current_file.parent.mkdir(parents=True, exist_ok=True)
        current_file.write_text("\n".join(lines), encoding="utf-8")
        files.append(current_file)

    return tmp_dir, files


def _run_subprocess(cmd: list[str], cwd: Path) -> tuple[str, str, int]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout, result.stderr, result.returncode


# ──────────────────────────────────────────────────────────────────────────────
# Tool: run_linter
# ──────────────────────────────────────────────────────────────────────────────

def run_linter(diff: str, repo_root: Path) -> dict:
    """
    Run ruff on files changed in the diff.
    Returns structured JSON findings.
    """
    with tracer.start_as_current_span("mcp.linter") as span:
        target_files = _extract_changed_files(diff, repo_root)
        use_temp = not target_files

        if use_temp:
            tmp_dir, target_files = _write_diff_as_temp_files(diff)
        else:
            tmp_dir = None

        if not target_files:
            return {"tool": "ruff", "findings": [], "summary": "No files to lint."}

        file_args = [str(f) for f in target_files]
        stdout, stderr, _ = _run_subprocess(
            [
                sys.executable, "-m", "ruff", "check",
                "--output-format=json",
                "--extend-select", "ANN",   # type annotation rules (ANN001/ANN201)
            ] + file_args,
            cwd=repo_root,
        )

        # Codes that are always artifacts when running on partial diff snippets:
        #   E999           — syntax error (can't parse incomplete file)
        #   invalid-syntax — ruff's non-numeric alias for parse errors
        #   F821           — undefined name (missing imports / context)
        #   F401           — unused import (diff may not include usage site)
        #   E1xx           — indentation errors (diff starts mid-block)
        #   E3xx           — blank-line rules (structural, need full file)
        #   W1xx/W3xx      — whitespace/blank-line warnings (same reason)
        _PARSE_ERROR_CODES = {"E999", "F821", "F401", "invalid-syntax"}
        _PARTIAL_PREFIX_SKIP = ("E1", "E3", "W1", "W3")

        findings = []
        try:
            raw = json.loads(stdout) if stdout.strip() else []
            for item in raw:
                code = item.get("code", "")
                # Skip parse/structural errors when running on temp files — they
                # are artifacts of incomplete snippets, not real code issues.
                if use_temp and (
                    code in _PARSE_ERROR_CODES
                    or any(code.startswith(p) for p in _PARTIAL_PREFIX_SKIP)
                ):
                    continue
                rel_path = _relativise(item.get("filename", ""), repo_root, tmp_dir)
                findings.append({
                    "id": f"ruff-{len(findings)+1:03d}",
                    "file": rel_path,
                    "line": item.get("location", {}).get("row"),
                    "col": item.get("location", {}).get("column"),
                    "severity": _ruff_severity(code),
                    "rule": f"ruff/{code or 'UNKNOWN'}",
                    "message": item.get("message", ""),
                    "raw": item.get("message", ""),
                })
        except json.JSONDecodeError:
            pass

        span.set_attribute("linter.findings", len(findings))

        if tmp_dir:
            import shutil
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        return {
            "tool": "ruff",
            "findings": findings,
            "partial_code": use_temp,  # True = ran on diff snippet, not full file
            "summary": f"{len(findings)} linting finding(s).",
        }


def _ruff_severity(code: str) -> str:
    if code.startswith("E") or code.startswith("F"):
        return "error"
    if code.startswith("W"):
        return "warning"
    if code.startswith("ANN"):
        return "warning"   # annotation rules → style warning, not error
    return "info"


# ──────────────────────────────────────────────────────────────────────────────
# Tool: run_type_checker
# ──────────────────────────────────────────────────────────────────────────────

def run_type_checker(diff: str, repo_root: Path) -> dict:
    """
    Run mypy on files changed in the diff.
    Returns structured JSON findings.
    """
    with tracer.start_as_current_span("mcp.type_checker") as span:
        target_files = _extract_changed_files(diff, repo_root)
        use_temp = not target_files

        if use_temp:
            tmp_dir, target_files = _write_diff_as_temp_files(diff)
        else:
            tmp_dir = None

        # Filter to Python files only
        py_files = [f for f in target_files if f.suffix == ".py"]

        if not py_files:
            return {"tool": "mypy", "findings": [], "summary": "No Python files to type-check."}

        file_args = [str(f) for f in py_files]
        stdout, stderr, _ = _run_subprocess(
            [sys.executable, "-m", "mypy", "--no-error-summary", "--show-column-numbers",
             "--ignore-missing-imports", "--no-strict-optional"] + file_args,
            cwd=repo_root,
        )

        # mypy error codes that indicate parse/import failures on partial snippets
        _MYPY_SKIP_CODES = {"syntax", "import", "import-untyped", "import-not-found"}

        findings = []
        # mypy output format: file:line:col: severity: message  [error-code]
        pattern = re.compile(
            r"^(.+?):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[(.+?)\])?$"
        )
        for line in (stdout + stderr).splitlines():
            m = pattern.match(line)
            if m:
                error_code = (m.group(6) or "").lower()
                # Skip parse/import errors on temp files — artifacts of partial snippets
                if use_temp and error_code in _MYPY_SKIP_CODES:
                    continue
                rel_path = _relativise(m.group(1), repo_root, tmp_dir)
                findings.append({
                    "id": f"mypy-{len(findings)+1:03d}",
                    "file": rel_path,
                    "line": int(m.group(2)),
                    "col": int(m.group(3)),
                    "severity": "error" if m.group(4) == "error" else "warning",
                    "rule": f"mypy/{m.group(6) or 'UNKNOWN'}",
                    "message": m.group(5),
                    "raw": line,
                })

        span.set_attribute("type_checker.findings", len(findings))

        if tmp_dir:
            import shutil
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        return {
            "tool": "mypy",
            "findings": findings,
            "partial_code": use_temp,
            "summary": f"{len(findings)} type error(s).",
        }


# ──────────────────────────────────────────────────────────────────────────────
# Tool: run_security_scanner
# ──────────────────────────────────────────────────────────────────────────────

def run_security_scanner(diff: str, repo_root: Path) -> dict:
    """
    Run bandit on files changed in the diff.
    Returns structured JSON findings.
    """
    with tracer.start_as_current_span("mcp.security_scanner") as span:
        target_files = _extract_changed_files(diff, repo_root)
        use_temp = not target_files

        if use_temp:
            tmp_dir, target_files = _write_diff_as_temp_files(diff)
        else:
            tmp_dir = None

        py_files = [f for f in target_files if f.suffix == ".py"]

        if not py_files:
            return {
                "tool": "bandit",
                "findings": [],
                "summary": "No Python files to scan.",
            }

        file_args = [str(f) for f in py_files]
        stdout, stderr, _ = _run_subprocess(
            [sys.executable, "-m", "bandit", "-f", "json", "-q"] + file_args,
            cwd=repo_root,
        )

        findings = []
        try:
            raw = json.loads(stdout) if stdout.strip() else {}
            for item in raw.get("results", []):
                rel_path = _relativise(item.get("filename", ""), repo_root, tmp_dir)
                findings.append({
                    "id": f"bandit-{len(findings)+1:03d}",
                    "file": rel_path,
                    "line": item.get("line_number"),
                    "severity": item.get("issue_severity", "MEDIUM").lower(),
                    "confidence": item.get("issue_confidence", "MEDIUM"),
                    "rule": f"bandit/{item.get('test_id', 'UNKNOWN')}",
                    "message": item.get("issue_text", ""),
                    "cwe": item.get("issue_cwe", {}).get("id"),
                    "raw": item.get("issue_text", ""),
                })
        except json.JSONDecodeError:
            pass

        span.set_attribute("security_scanner.findings", len(findings))

        if tmp_dir:
            import shutil
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        return {
            "tool": "bandit",
            "findings": findings,
            "partial_code": use_temp,
            "summary": f"{len(findings)} security finding(s).",
        }


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _relativise(path_str: str, repo_root: Path, tmp_dir: Path | None) -> str:
    """Return a clean relative path string for display."""
    p = Path(path_str)
    try:
        if tmp_dir and p.is_relative_to(tmp_dir):
            return str(p.relative_to(tmp_dir))
        if p.is_relative_to(repo_root):
            return str(p.relative_to(repo_root))
    except ValueError:
        pass
    return path_str


# ──────────────────────────────────────────────────────────────────────────────
# FastMCP server registration (for `python main.py serve`)
# ──────────────────────────────────────────────────────────────────────────────

if _mcp is not None:

    @_mcp.tool()
    def mcp_run_linter(diff: str, repo_root: str) -> dict:
        """Run ruff linter on files changed in the diff. Returns structured findings."""
        return run_linter(diff, Path(repo_root))

    @_mcp.tool()
    def mcp_run_type_checker(diff: str, repo_root: str) -> dict:
        """Run mypy type checker on Python files changed in the diff."""
        return run_type_checker(diff, Path(repo_root))

    @_mcp.tool()
    def mcp_run_security_scanner(diff: str, repo_root: str) -> dict:
        """Run bandit security scanner on Python files changed in the diff."""
        return run_security_scanner(diff, Path(repo_root))


def get_mcp_server():
    return _mcp
