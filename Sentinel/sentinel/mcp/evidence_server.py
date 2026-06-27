"""
Sentinel MCP Evidence Server
Wraps deterministic static analysis tools as MCP tools.
Every tool returns structured evidence that agents can cite.
No LLM judgment here — only facts.
"""
import os
import subprocess
import json
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("sentinel-evidence-server")

# Targets must resolve inside this root. Defaults to the Sentinel repo so the
# bundled eval corpus (targets/) and self-review demo (sentinel/) both work.
# Override with SENTINEL_SCAN_ROOT for a different deployment layout.
SCAN_ROOT = Path(os.environ.get(
    "SENTINEL_SCAN_ROOT", Path(__file__).parent.parent.parent
)).resolve()

# Guard against a target large enough to wedge a tool subprocess past its
# timeout (or a hostile target with millions of tiny files). Override with
# SENTINEL_MAX_SCAN_FILES / SENTINEL_MAX_SCAN_BYTES for larger deployments.
MAX_SCAN_FILES = int(os.environ.get("SENTINEL_MAX_SCAN_FILES", 5000))
MAX_SCAN_BYTES = int(os.environ.get("SENTINEL_MAX_SCAN_BYTES", 200 * 1024 * 1024))


class InvalidTargetPath(Exception):
    pass


def _validate_target(target_path: str) -> Path:
    """
    Resolve target_path and ensure it's an existing directory inside
    SCAN_ROOT, within file-count/size limits. Prevents an A2A caller from
    pointing the scanner (and its subprocess invocations) at arbitrary or
    oversized filesystem paths.
    """
    resolved = (SCAN_ROOT / target_path).resolve() if not Path(target_path).is_absolute() \
        else Path(target_path).resolve()

    if resolved != SCAN_ROOT and SCAN_ROOT not in resolved.parents:
        raise InvalidTargetPath(
            f"target_path '{target_path}' resolves outside the allowed "
            f"scan root '{SCAN_ROOT}'"
        )
    if not resolved.exists() or not resolved.is_dir():
        raise InvalidTargetPath(f"target_path '{target_path}' is not a directory")

    file_count = 0
    total_bytes = 0
    for f in resolved.rglob("*"):
        if f.is_file():
            file_count += 1
            total_bytes += f.stat().st_size
            if file_count > MAX_SCAN_FILES or total_bytes > MAX_SCAN_BYTES:
                raise InvalidTargetPath(
                    f"target_path '{target_path}' exceeds scan limits "
                    f"({MAX_SCAN_FILES} files / {MAX_SCAN_BYTES} bytes)"
                )
    return resolved


def _run(cmd: list[str], cwd: str | None = None) -> dict:
    """Run a subprocess and return structured output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=60,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


@mcp.tool()
def lint_scan(target_path: str) -> dict:
    """
    Run ruff linter on target path.
    Returns style and error findings with line locators.
    """
    try:
        safe_target = str(_validate_target(target_path))
    except InvalidTargetPath as e:
        return {"tool": "ruff", "target": target_path, "returncode": -1,
                "findings": [], "raw_stderr": str(e)}

    result = _run(
        ["ruff", "check", safe_target, "--output-format", "json"],
    )
    try:
        findings = json.loads(result["stdout"]) if result["stdout"] else []
    except json.JSONDecodeError:
        findings = []

    return {
        "tool": "ruff",
        "target": target_path,
        "returncode": result["returncode"],
        "findings": findings,
        "raw_stderr": result["stderr"],
    }


@mcp.tool()
def security_scan(target_path: str) -> dict:
    """
    Run bandit security scanner on target path.
    Returns known insecure patterns: eval, pickle, subprocess, hardcoded secrets.
    """
    try:
        safe_target = str(_validate_target(target_path))
    except InvalidTargetPath as e:
        return {"tool": "bandit", "target": target_path, "returncode": -1,
                "findings": [], "metrics": {}, "raw_stderr": str(e)}

    result = _run(
        ["bandit", "-r", safe_target, "-f", "json", "-q"],
    )
    try:
        parsed = json.loads(result["stdout"]) if result["stdout"] else {}
    except json.JSONDecodeError:
        parsed = {}

    issues = parsed.get("results", [])
    return {
        "tool": "bandit",
        "target": target_path,
        "returncode": result["returncode"],
        "findings": issues,
        "metrics": parsed.get("metrics", {}),
    }


@mcp.tool()
def dependency_scan(target_path: str) -> dict:
    """
    Run pip-audit on target path to find dependency CVEs.
    Returns known vulnerabilities in installed or requirements.txt packages.
    """
    try:
        safe_target = _validate_target(target_path)
    except InvalidTargetPath as e:
        return {"tool": "pip_audit", "target": target_path, "returncode": -1,
                "vulnerabilities": [], "raw_stderr": str(e)}

    req_file = safe_target / "requirements.txt"

    if req_file.exists():
        cmd = ["pip-audit", "-r", str(req_file), "-f", "json"]
    else:
        cmd = ["pip-audit", "-f", "json"]

    result = _run(cmd)
    try:
        parsed = json.loads(result["stdout"]) if result["stdout"] else []
    except json.JSONDecodeError:
        parsed = []

    return {
        "tool": "pip_audit",
        "target": target_path,
        "returncode": result["returncode"],
        "vulnerabilities": parsed,
    }


if __name__ == "__main__":
    mcp.run()