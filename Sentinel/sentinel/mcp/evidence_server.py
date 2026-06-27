"""
Sentinel MCP Evidence Server
Wraps deterministic static analysis tools as MCP tools.
Every tool returns structured evidence that agents can cite.
No LLM judgment here — only facts.
"""
import subprocess
import json
import sys
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("sentinel-evidence-server")


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
    result = _run(
        ["ruff", "check", target_path, "--output-format", "json"],
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
    result = _run(
        ["bandit", "-r", target_path, "-f", "json", "-q"],
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
    req_file = Path(target_path) / "requirements.txt"

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