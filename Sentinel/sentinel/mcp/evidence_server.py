"""
Sentinel MCP Evidence Server
Wraps deterministic static analysis tools as MCP tools.
Every tool returns structured evidence that agents can cite.
No LLM judgment here — only facts.

Fail-closed contract: every tool result carries an explicit "status":
  ok       — the scanner ran and its output parsed
  missing  — the scanner executable could not be resolved
  timeout  — the scanner exceeded its wall-clock budget
  error    — the scanner ran but failed (bad exit code / unparseable output,
             or the input was refused, e.g. unpinned requirements)
  skipped  — nothing to scan (pip-audit with no requirements.txt); recorded,
             but not a scan failure
The pipeline turns anything other than ok/skipped into an "inconclusive"
verdict — an empty findings list from a scanner that never ran is never
reported as a pass.
"""
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import json
import time
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

# Sentinel's own bandit INI. Passing it explicitly (--ini) stops bandit from
# picking up a `.bandit` file shipped inside the target, which could
# otherwise skip tests and silence findings.
_BANDIT_INI = Path(__file__).parent / "bandit_sentinel.ini"


class InvalidTargetPath(Exception):
    pass


def _validate_target(target_path: str | Path) -> Path:
    """
    Resolve target_path and ensure it's an existing directory inside
    SCAN_ROOT, within file-count/size limits. Prevents an A2A caller from
    pointing the scanner (and its subprocess invocations) at arbitrary or
    oversized filesystem paths. Relative paths resolve against SCAN_ROOT
    (never the process CWD), so every component sees the same directory.
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


def resolve_scanner(name: str) -> str | None:
    """
    Locate a scanner executable. The running interpreter's own scripts
    directory is checked first, so scanners installed into Sentinel's venv
    are found even when the venv isn't activated (bare names aren't on PATH
    then); shutil.which is the fallback. Returns None if not found — the
    caller reports that as status "missing", never as "no findings".
    """
    dirs = [Path(sys.executable).parent]
    scripts = sysconfig.get_path("scripts")
    if scripts:
        dirs.append(Path(scripts))
    suffixes = [".exe", ""] if os.name == "nt" else [""]
    for d in dirs:
        for suffix in suffixes:
            candidate = d / f"{name}{suffix}"
            if candidate.is_file():
                return str(candidate)
    return shutil.which(name)


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> dict:
    """Run a scanner subprocess and return structured output.

    cmd[0] is the scanner's bare name; it is resolved via resolve_scanner.
    The result always has a "status" of "missing" / "timeout" / "ran" so
    callers can never confuse "tool absent" with "tool found nothing".

    Explicit utf-8 decoding (errors="replace") because some tools (e.g.
    semgrep) emit non-cp1252 bytes, and Windows' default subprocess text
    decoding uses the console's locale codec and would otherwise crash.
    """
    exe = resolve_scanner(cmd[0])
    if exe is None:
        return {"status": "missing", "returncode": -1, "stdout": "",
                "stderr": f"{cmd[0]}: executable not found"}
    try:
        result = subprocess.run(
            [exe, *cmd[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout,
        )
        return {
            "status": "ran",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": -1, "stdout": "",
                "stderr": f"{cmd[0]}: timed out after {timeout}s"}
    except (FileNotFoundError, PermissionError, OSError) as e:
        return {"status": "missing", "returncode": -1, "stdout": "", "stderr": str(e)}


def _parse_json_output(result: dict, ok_returncodes: tuple[int, ...]):
    """
    Turn a _run result into (status, parsed_json, detail). A scanner counts
    as "ok" only if it exited with an expected code AND produced parseable
    JSON — a crash that printed nothing must not look like a clean scan.
    """
    if result.get("status") in ("missing", "timeout"):
        return result["status"], None, result.get("stderr", "")
    rc = result.get("returncode", -1)
    stdout = result.get("stdout") or ""
    try:
        parsed = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    if parsed is None:
        return "error", None, f"rc={rc}, no JSON output: {result.get('stderr', '')[:300]}"
    if rc not in ok_returncodes:
        return "error", parsed, f"rc={rc}: {result.get('stderr', '')[:300]}"
    return "ok", parsed, ""


def _invalid(tool: str, target_path: str, e: Exception, **empty) -> dict:
    return {"tool": tool, "target": str(target_path), "status": "error",
            "detail": f"invalid target: {e}", "returncode": -1,
            "raw_stderr": str(e), **empty}


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
# A registry outage would otherwise add a 120-second timeout to every target
# in a batch. After a failure the registry group is skipped for a bounded
# back-off window (not for the life of the process), then retried.
REGISTRY_RETRY_SECONDS = int(os.environ.get("SENTINEL_SEMGREP_REGISTRY_RETRY_SECONDS", 300))
_registry_failed_at: float | None = None


def _now() -> float:
    return time.monotonic()


def _is_registry_group(group: list[str]) -> bool:
    return all(cfg.startswith(("p/", "r/")) for cfg in group)


def lint_scan(target_path: str) -> dict:
    """
    Run ruff linter on target path.
    Returns style and error findings with line locators.
    """
    try:
        safe_target = str(_validate_target(target_path))
    except InvalidTargetPath as e:
        return _invalid("ruff", target_path, e, findings=[])

    # --isolated: ignore any ruff config shipped inside the target.
    result = _run(
        ["ruff", "check", safe_target, "--isolated", "--output-format", "json"],
    )
    # ruff: 0 = clean, 1 = violations found, 2 = ruff itself failed
    status, parsed, detail = _parse_json_output(result, ok_returncodes=(0, 1))
    findings = parsed if isinstance(parsed, list) else []

    return {
        "tool": "ruff",
        "target": target_path,
        "status": status,
        "detail": detail,
        "returncode": result["returncode"],
        "findings": findings,
        "raw_stderr": result["stderr"][:500],
    }


def security_scan(target_path: str) -> dict:
    """
    Run bandit security scanner on target path.
    Returns known insecure patterns: eval, pickle, subprocess, hardcoded secrets.
    """
    try:
        safe_target = str(_validate_target(target_path))
    except InvalidTargetPath as e:
        return _invalid("bandit", target_path, e, findings=[], metrics={})

    # --ini: Sentinel's own config, so a target-supplied .bandit can't skip
    # tests. --ignore-nosec: a target can't silence findings with `# nosec`.
    result = _run(
        ["bandit", "-r", safe_target, "-f", "json", "-q",
         "--ini", str(_BANDIT_INI), "--ignore-nosec"],
    )
    # bandit: 0 = no issues, 1 = issues found, anything else = failure
    status, parsed, detail = _parse_json_output(result, ok_returncodes=(0, 1))
    parsed = parsed if isinstance(parsed, dict) else {}

    return {
        "tool": "bandit",
        "target": target_path,
        "status": status,
        "detail": detail,
        "returncode": result["returncode"],
        "findings": parsed.get("results", []),
        "metrics": parsed.get("metrics", {}),
        # Per-file parse errors don't void the scan; surface them as warnings.
        "warnings": [str(e)[:200] for e in parsed.get("errors", [])],
        "raw_stderr": result["stderr"][:500],
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
    rules too even though they need no network at all.

    Status: "ok" when every local (non-registry) group produced a results
    JSON. Per-file parse errors inside a successful run are kept as
    warnings — they never discard the group's results. Registry groups are
    best-effort: their failure is a warning, not a scan failure. If semgrep
    can't be resolved at all (e.g. native Windows, where it doesn't run),
    the status is "missing" — never a silent empty result.
    """
    try:
        safe_target = str(_validate_target(target_path))
    except InvalidTargetPath as e:
        return _invalid("semgrep", target_path, e, findings=[])

    global _registry_failed_at

    all_findings = []
    warnings = []
    local_failures = []  # (status, detail)

    for group in SEMGREP_CONFIG_GROUPS:
        is_registry = _is_registry_group(group)
        label = ",".join(group)
        if is_registry and _registry_failed_at is not None \
                and _now() - _registry_failed_at < REGISTRY_RETRY_SECONDS:
            warnings.append(f"[{label}] skipped: registry fetch failed recently")
            continue

        cmd = ["semgrep"]
        for cfg in group:
            cmd += ["--config", cfg]
        # --metrics=off skips semgrep's telemetry/version-check network
        # call. --disable-nosem: a target can't silence rules with
        # `# nosemgrep` comments.
        cmd += ["--json", "--quiet", "--no-git-ignore", "--metrics=off",
                "--disable-nosem", safe_target]
        # First run of a registry pack may need to fetch it; allow more
        # time than the other tools' default 60s.
        result = _run(cmd, timeout=120)
        if result.get("status") == "missing":
            return {"tool": "semgrep", "target": target_path, "status": "missing",
                    "detail": result["stderr"], "returncode": -1, "findings": [],
                    "warnings": warnings, "raw_stderr": result["stderr"][:500]}

        try:
            parsed = json.loads(result["stdout"]) if result["stdout"] else None
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict) and parsed.get("results") is not None:
            all_findings.extend(parsed["results"])
            for err in parsed.get("errors") or []:
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                warnings.append(f"[{label}] {str(msg)[:200]}")
            if is_registry:
                _registry_failed_at = None
        else:
            detail = f"[{label}] rc={result['returncode']}: {result['stderr'][:200]}"
            if is_registry:
                _registry_failed_at = _now()
                warnings.append(detail)
            else:
                local_failures.append((result.get("status"), detail))

    if local_failures:
        status = "timeout" if all(s == "timeout" for s, _ in local_failures) else "error"
        detail = " | ".join(d for _, d in local_failures)[:500]
    else:
        status, detail = "ok", ""

    return {
        "tool": "semgrep",
        "target": target_path,
        "status": status,
        "detail": detail,
        "returncode": 0 if status == "ok" else -1,
        "findings": all_findings,
        "warnings": warnings,
        "raw_stderr": " | ".join(warnings)[:500],
    }


# A requirements line pip-audit can audit WITHOUT building anything:
# `name==version`, optional extras, optional env marker, optional hashes.
_PINNED_REQ = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,\s-]+\])?"
    r"\s*==\s*[A-Za-z0-9][A-Za-z0-9.!+_-]*"
    r"(\s*;[^-]*?)?"
    r"(\s+--hash=[A-Za-z0-9]+:[A-Fa-f0-9]+)*\s*$"
)


def _unpinned_requirement_lines(req_file: Path) -> list[str]:
    """
    Return the requirement lines that are NOT strictly pinned. `pip-audit -r`
    otherwise hands the file to pip, which can build sdists / editable
    installs — i.e. execute the target's build code. Any option line
    (-e, -r, -c, --index-url, ...), path, or URL is rejected.
    """
    text = req_file.read_text(encoding="utf-8", errors="replace")
    logical = text.replace("\\\r\n", " ").replace("\\\n", " ")
    bad = []
    for raw_line in logical.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw_line).strip()
        if not line:
            continue
        if not _PINNED_REQ.match(line):
            bad.append(line[:120])
    return bad


def dependency_scan(target_path: str) -> dict:
    """
    Run pip-audit against the target's requirements.txt to find dependency
    vulnerabilities. Only strictly pinned requirement files are audited, with
    --no-deps --disable-pip so nothing from the target is ever installed or
    built. No requirements.txt => status "skipped" (Sentinel never audits its
    own environment in place of the target's).
    """
    try:
        safe_target = _validate_target(target_path)
    except InvalidTargetPath as e:
        return _invalid("pip_audit", target_path, e, vulnerabilities=[])

    req_file = safe_target / "requirements.txt"
    if not req_file.is_file():
        return {"tool": "pip_audit", "target": target_path, "status": "skipped",
                "detail": "no-manifest: no requirements.txt in target",
                "returncode": 0, "vulnerabilities": []}

    unpinned = _unpinned_requirement_lines(req_file)
    if unpinned:
        return {"tool": "pip_audit", "target": target_path, "status": "error",
                "detail": f"unpinned requirements, not audited: {unpinned[:5]}",
                "returncode": -1, "vulnerabilities": []}

    cmd = ["pip-audit", "-r", str(req_file), "--no-deps", "--disable-pip",
           "--progress-spinner", "off", "-f", "json"]
    result = _run(cmd)
    # pip-audit: 0 = no known vulns, 1 = vulns found
    status, parsed, detail = _parse_json_output(result, ok_returncodes=(0, 1))

    return {
        "tool": "pip_audit",
        "target": target_path,
        "status": status,
        "detail": detail,
        "returncode": result["returncode"],
        # Raw pip-audit JSON: {"dependencies": [...], "fixes": [...]} on
        # current pip-audit, a bare list of dependencies on older versions.
        "vulnerabilities": parsed if parsed is not None else [],
        "raw_stderr": result["stderr"][:500],
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
