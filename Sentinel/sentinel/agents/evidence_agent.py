"""
Evidence Agent — Deterministic Evidence Collector.

Calls MCP tools (bandit, ruff, pip-audit, semgrep) and converts their
raw output into structured Evidence objects with unique IDs.

No LLM judgment here. This agent produces only facts.
Every evidence item gets an ID that findings must reference. IDs are
content-addressed (hash of tool + location + rule), so re-scanning the same
target yields the same IDs — which is what lets produce_attestation re-run
the scan server-side instead of trusting caller-supplied evidence.

Alongside the evidence, collect_evidence_with_status reports each tool's
status (ok / missing / timeout / error / skipped) so the pipeline can fail
closed: a scanner that didn't run is never mistaken for "no findings".
"""
import asyncio
import concurrent.futures
import hashlib
from fastmcp import Client
from sentinel.models.schemas import Evidence
from sentinel.mcp.evidence_server import mcp

# Evidence.source name for each MCP tool result key.
TOOL_SOURCES = {
    "security": "bandit",
    "lint": "ruff",
    "dependency": "pip_audit",
    "semgrep": "semgrep",
}


def _run_async(coro):
    """
    Run a coroutine to completion regardless of whether we're already
    inside a running event loop (e.g. called from an async FastAPI
    background task) or a plain sync context (CLI, pytest, eval runner).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


async def _call_evidence_tools(target_path: str) -> dict:
    """
    Call the MCP evidence server's tools over a real (in-memory) MCP
    transport, rather than invoking the decorated functions directly.
    This exercises the actual MCP protocol path.
    """
    async with Client(mcp) as client:
        sec, lint, dep, semgrep = await asyncio.gather(
            client.call_tool("security_scan", {"target_path": target_path}),
            client.call_tool("lint_scan", {"target_path": target_path}),
            client.call_tool("dependency_scan", {"target_path": target_path}),
            client.call_tool("semgrep_scan", {"target_path": target_path}),
        )
    return {
        "security": sec.data,
        "lint": lint.data,
        "dependency": dep.data,
        "semgrep": semgrep.data,
    }


def _evidence_id(prefix: str, *parts) -> str:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"ev_{prefix}_{digest[:12]}"


def iter_pip_audit_dependencies(raw) -> list[dict]:
    """
    Normalize pip-audit JSON to a list of dependency dicts
    ({"name", "version", "vulns": [...]}). Current pip-audit emits
    {"dependencies": [...], "fixes": [...]}; older versions emitted the bare
    list. Iterating the dict form directly walks its keys and silently
    records zero vulnerabilities — that was a real bug.
    """
    if isinstance(raw, dict):
        raw = raw.get("dependencies", [])
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict)]


def _tool_status(result: dict) -> dict:
    status = result.get("status")
    if status is None:
        # Defensive: a result without a status is never treated as clean.
        status = "error"
    return {
        "status": status,
        "detail": str(result.get("detail", ""))[:500],
        "warnings": list(result.get("warnings", []))[:20],
    }


def evidence_from_tool_results(tool_results: dict, target_path: str) -> list[Evidence]:
    """Convert raw MCP tool results into Evidence objects (deduplicated by id)."""
    evidence: dict[str, Evidence] = {}

    def _add(ev: Evidence):
        evidence.setdefault(ev.evidence_id, ev)

    # --- bandit ---
    for issue in tool_results["security"].get("findings", []):
        filename = issue.get("filename", target_path)
        line = issue.get("line_number", 0)
        _add(Evidence(
            evidence_id=_evidence_id("bandit", filename, line, issue.get("col_offset", 0),
                                     issue.get("test_id")),
            source="bandit",
            locator=f"{filename}:{line}",
            raw={
                "test_id": issue.get("test_id"),
                "test_name": issue.get("test_name"),
                "issue_severity": issue.get("issue_severity"),
                "issue_confidence": issue.get("issue_confidence"),
                "issue_text": issue.get("issue_text"),
                "cwe_id": (issue.get("issue_cwe") or {}).get("id"),
            },
        ))

    # --- ruff ---
    for issue in tool_results["lint"].get("findings", []):
        filename = issue.get("filename", target_path)
        loc = issue.get("location") or {}
        _add(Evidence(
            evidence_id=_evidence_id("ruff", filename, loc.get("row", 0), loc.get("column", 0),
                                     issue.get("code")),
            source="ruff",
            locator=f"{filename}:{loc.get('row', 0)}",
            raw={
                "code": issue.get("code"),
                "message": issue.get("message"),
                "fix": issue.get("fix"),
            },
        ))

    # --- pip-audit ---
    for dep in iter_pip_audit_dependencies(tool_results["dependency"].get("vulnerabilities")):
        for vuln in dep.get("vulns", []) or []:
            if not isinstance(vuln, dict):
                continue
            _add(Evidence(
                evidence_id=_evidence_id("pipaudit", dep.get("name"), dep.get("version"),
                                         vuln.get("id")),
                source="pip_audit",
                locator=f"{dep.get('name', 'unknown')}=={dep.get('version', '?')}",
                raw={
                    "package": dep.get("name"),
                    "version": dep.get("version"),
                    "vuln_id": vuln.get("id"),
                    "aliases": vuln.get("aliases", []) or [],
                    "description": (vuln.get("description") or "")[:200],
                    "fix_versions": vuln.get("fix_versions", []) or [],
                },
            ))

    # --- semgrep ---
    for issue in tool_results["semgrep"].get("findings", []):
        extra = issue.get("extra", {})
        path = issue.get("path", target_path)
        start = issue.get("start") or {}
        _add(Evidence(
            evidence_id=_evidence_id("semgrep", path, start.get("line", 0), start.get("col", 0),
                                     issue.get("check_id")),
            source="semgrep",
            locator=f"{path}:{start.get('line', 0)}",
            raw={
                "check_id": issue.get("check_id"),
                "message": extra.get("message", "")[:300],
                "severity": extra.get("severity"),
                "metadata": extra.get("metadata", {}),
            },
        ))

    return list(evidence.values())


def collect_evidence_with_status(target_path: str) -> tuple[list[Evidence], dict]:
    """
    Run all deterministic tools against the target (over the real MCP
    transport, in a single batched call). Returns (evidence, tool_status)
    where tool_status maps each Evidence source name ("bandit", "ruff",
    "pip_audit", "semgrep") to {"status", "detail", "warnings"}.
    """
    print(f"\n[EvidenceAgent] Scanning: {target_path}")
    print("-" * 50)

    tool_results = _run_async(_call_evidence_tools(str(target_path)))
    tool_status = {
        TOOL_SOURCES[key]: _tool_status(result) for key, result in tool_results.items()
    }
    evidence_list = evidence_from_tool_results(tool_results, str(target_path))

    for source, st in tool_status.items():
        count = sum(1 for e in evidence_list if e.source == source)
        suffix = f" — {st['detail']}" if st["detail"] else ""
        print(f"[EvidenceAgent] {source}: status={st['status']}, {count} evidence items{suffix}")
    print(f"[EvidenceAgent] Total evidence collected: {len(evidence_list)}")
    print("-" * 50)

    return evidence_list, tool_status


def collect_evidence(target_path: str) -> list[Evidence]:
    """
    Evidence only (no tool status). Callers that produce a verdict must use
    collect_evidence_with_status so a missing scanner can't read as a pass.
    """
    return collect_evidence_with_status(target_path)[0]
