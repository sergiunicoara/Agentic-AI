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


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> dict:
    """Run a subprocess and return structured output.

    Explicit utf-8 decoding (errors="replace") because some tools (e.g.
    semgrep) emit non-cp1252 bytes, and Windows' default subprocess text
    decoding uses the console's locale codec and would otherwise crash.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout,
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


# Custom Sentinel rules (SSRF, LLM-key-by-value-format) live alongside this
# file. Combined with two registry packs for broad Python security + secret
# coverage. The registry packs are fetched from semgrep's registry on first
# use and cached locally afterward — see README "Offline / no-network use".
#
# Grouped into two configs (not one per pack) as a deliberate tradeoff: one
# semgrep subprocess per group, so local rules — which need no network —
# run in their own invocation and survive a registry outage, without
# paying full per-invocation startup cost for every individual pack.
_SEMGREP_RULES_DIR = Path(__file__).parent / "semgrep_rules"
SEMGREP_CONFIG_GROUPS = [
    [str(_SEMGREP_RULES_DIR)],       # local, no network — always runs
    ["p/python", "p/gitleaks"],      # registry packs — best-effort
]


_REGISTRY_CONFIG_GROUP = ["p/python", "p/gitleaks"]
_registry_packs_unavailable = False


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


def semgrep_scan(target_path: str) -> dict:
    """
    Run semgrep on target path: project-specific rules (SSRF via
    unvalidated URL, LLM/cloud API keys by value format — see
    sentinel/mcp/semgrep_rules/agent_security.yaml) plus the p/python and
    p/gitleaks registry packs. Catches patterns bandit has no rule for at
    all (data-flow issues like SSRF; key formats independent of variable
    naming).

    Each config GROUP (see SEMGREP_CONFIG_GROUPS) runs as its own semgrep
    invocation rather than one call with every --config flag: semgrep
    fails an entire run if even one config (e.g. a registry pack) can't
    be fetched, which would silently zero out the project's own local
    rules too even though they need no network at all. Running the local
    group separately means a failed/offline registry group only drops
    that group's findings — local rules still contribute regardless.
    Degrades gracefully overall: if semgrep isn't installed, every
    invocation returns no findings instead of failing the pipeline —
    semgrep is additive evidence, not a hard dependency.
    """
    try:
        safe_target = str(_validate_target(target_path))
    except InvalidTargetPath as e:
        return {"tool": "semgrep", "target": target_path, "returncode": -1,
                "findings": [], "raw_stderr": str(e)}

    global _registry_packs_unavailable

    all_findings = []
    stderr_parts = []
    any_succeeded = False

    for group in SEMGREP_CONFIG_GROUPS:
        # A registry outage can otherwise add a 120-second timeout to every
        # target in a batch. Local rules still run for every target.
        if group == _REGISTRY_CONFIG_GROUP and _registry_packs_unavailable:
            stderr_parts.append(
                "[p/python,p/gitleaks] skipped after an earlier registry fetch failure"
            )
            continue

        cmd = ["semgrep"]
        for cfg in group:
            cmd += ["--config", cfg]
        # --metrics=off skips semgrep's telemetry/version-check network
        # call, which otherwise adds several seconds to every invocation.
        cmd += ["--json", "--quiet", "--no-git-ignore", "--metrics=off", safe_target]
        # First run of a registry pack may need to fetch it; allow more
        # time than the other tools' default 60s.
        result = _run(cmd, timeout=120)
        try:
            parsed = json.loads(result["stdout"]) if result["stdout"] else {}
        except json.JSONDecodeError:
            parsed = {}

        if parsed.get("results") is not None and not parsed.get("errors"):
            any_succeeded = True
            all_findings.extend(parsed["results"])
        else:
            if group == _REGISTRY_CONFIG_GROUP:
                _registry_packs_unavailable = True
            if result["stderr"]:
                stderr_parts.append(f"[{','.join(group)}] {result['stderr'][:200]}")

    return {
        "tool": "semgrep",
        "target": target_path,
        "returncode": 0 if any_succeeded else -1,
        "findings": all_findings,
        "raw_stderr": " | ".join(stderr_parts)[:500],
    }


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


# Registered by calling the tool()-decorator's return value as a plain
# function (not via @mcp.tool() syntax) so the module-level names above
# stay bound to plain, directly-callable functions (used by tests and
# anything calling them outside the MCP transport) while still being
# exposed as real MCP tools for Client.call_tool().
mcp.tool()(lint_scan)
mcp.tool()(security_scan)
mcp.tool()(semgrep_scan)
mcp.tool()(dependency_scan)


if __name__ == "__main__":
    mcp.run()
