"""
Live Red Team Runner — actually executes corpus payloads against the
target's real functions, instead of only checking for static surfaces
(sentinel.redteam.runner does the static check; this is the live one).

SAFETY MODEL — read before enabling (opt-in only, never on by default):
- Restricted to targets inside the same allow-list the MCP evidence server
  enforces (SCAN_ROOT in sentinel/mcp/evidence_server.py). This is built
  for the bundled, trusted target corpus — not for scanning arbitrary
  third-party code live.
- Target code is NEVER imported or called in the main Sentinel process.
  Both discovery (which functions exist) and invocation (calling one with
  a payload) happen inside sentinel.redteam._live_worker, in its own
  subprocess, every single time.
- Each subprocess gets:
    * a fresh, disposable temp directory as its cwd — any file writes or
      deletes the target code performs land there, not in the real
      filesystem, and the directory is deleted afterward
    * a scrubbed environment (no inherited secrets/credentials)
    * network sockets patched to raise immediately — no real egress,
      even if the target tries to call out to a real API
    * a hard wall-clock timeout
    * (POSIX only) CPU-time and address-space rlimits
- Only functions whose first required parameter looks like free-form text
  (str/bytes, and NOT named like a path — "path"/"dir"/"file"/"filename")
  are ever called with a raw adversarial payload. This is enforced inside
  the worker itself, so a payload can never reach a filesystem-path
  parameter regardless of what the corpus contains.
- Total invocations per run are capped (MAX_LIVE_INVOCATIONS).

This is best-effort isolation appropriate for the bundled demo/eval
corpus. It is NOT a substitute for a real container/VM sandbox (gVisor,
firecracker, etc.) if you ever point this at untrusted code.
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid
import shutil
from pathlib import Path

from sentinel.mcp.evidence_server import _validate_target, InvalidTargetPath
from sentinel.redteam.corpus import get_all_payloads
from sentinel.models.schemas import Evidence

MAX_LIVE_INVOCATIONS = 16
PER_CALL_TIMEOUT = 5  # seconds, wall-clock, enforced by the parent process

# The repo root, so `python -m sentinel.redteam._live_worker` resolves even
# though the worker's cwd is a disposable temp directory, not the repo.
_REPO_ROOT = str(Path(__file__).parent.parent.parent)


def _sandbox_env() -> dict:
    """Scrubbed environment: no inherited GOOGLE_*, API keys, etc. — just
    enough to spawn the interpreter and resolve the sentinel package."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": _REPO_ROOT}
    if os.environ.get("SystemRoot"):
        env["SystemRoot"] = os.environ["SystemRoot"]  # required for Windows subprocess spawn
    return env


def _discover_callable_targets(py_file: Path) -> list[tuple[str, str]]:
    """Ask the (sandboxed) worker which functions in py_file are safe to call."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "sentinel.redteam._live_worker", "--discover", str(py_file)],
            capture_output=True, text=True, timeout=PER_CALL_TIMEOUT,
            cwd=_REPO_ROOT, env=_sandbox_env(),
        )
        lines = proc.stdout.strip().splitlines()
        if not lines:
            return []
        return [tuple(x) for x in json.loads(lines[-1])]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, IndexError):
        return []


def _run_in_sandbox(py_file: Path, func_name: str, param_kind: str, payload: str) -> dict:
    """Spawn the live-worker subprocess for one (function, payload) pair."""
    work_dir = tempfile.mkdtemp(prefix="sentinel_live_")
    try:
        payload_file = Path(work_dir) / "payload.txt"
        payload_file.write_text(payload, encoding="utf-8")
        env = _sandbox_env()

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "sentinel.redteam._live_worker",
                 str(py_file), func_name, param_kind, str(payload_file)],
                cwd=work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=PER_CALL_TIMEOUT,
            )
            lines = proc.stdout.strip().splitlines()
            if not lines:
                return {"status": "no_output", "stderr": proc.stderr[:500]}
            try:
                return json.loads(lines[-1])
            except json.JSONDecodeError:
                return {"status": "unparseable_output", "raw": lines[-1][:500]}
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_live_red_team(target_path: str) -> dict:
    """
    Fire the red team corpus at the target's real code, for real, inside
    the sandbox described in this module's docstring.

    Returns a summary plus trajectory evidence (raw["mode"]="live") for
    every payload that actually executed against a real function without
    the sandbox itself intervening (timeout doesn't count as confirmed;
    completing OR raising a normal exception both do — either way the
    code path ran with attacker-controlled input).
    """
    try:
        safe_target = _validate_target(target_path)
    except InvalidTargetPath as e:
        print(f"\n[LiveRedTeam] Blocked: {e}")
        return {
            "target": target_path, "total_invocations": 0, "live_confirmed": 0,
            "results": [], "trajectory_evidence": [], "blocked_reason": str(e),
        }

    print(f"\n[LiveRedTeam] Starting live (sandboxed) red team assessment: {target_path}")
    print("-" * 50)

    payloads = get_all_payloads()
    combos = []
    for py_file in sorted(safe_target.rglob("*.py")):
        for func_name, param_kind in _discover_callable_targets(py_file):
            for payload in payloads:
                combos.append((py_file, func_name, param_kind, payload))

    if len(combos) > MAX_LIVE_INVOCATIONS:
        print(f"[LiveRedTeam] {len(combos)} (function, payload) combinations found, "
              f"capping at {MAX_LIVE_INVOCATIONS}")
    combos = combos[:MAX_LIVE_INVOCATIONS]

    results = []
    trajectory_evidence = []
    live_confirmed = 0

    for py_file, func_name, param_kind, payload in combos:
        outcome = _run_in_sandbox(py_file, func_name, param_kind, payload["payload"])
        status = outcome.get("status", "unknown")
        # A network-blocked exception means the sandbox intervened — that
        # proves containment, not that the gadget genuinely fired.
        confirmed = status in ("completed", "raised_exception") and not outcome.get("network_blocked")

        results.append({
            "payload_id": payload["id"],
            "name": payload["name"],
            "function": f"{py_file.name}:{func_name}",
            "status": status,
            "network_blocked": outcome.get("network_blocked", False),
            "live_confirmed": confirmed,
        })

        if outcome.get("network_blocked"):
            label = "NETWORK-BLOCKED"
        elif confirmed:
            label = "LIVE-CONFIRMED"
        else:
            label = status.upper()
        print(f"  [{label}] {payload['name']} -> {py_file.name}:{func_name}()")

        if confirmed:
            live_confirmed += 1
            ev = Evidence(
                evidence_id=f"ev_redteam_{uuid.uuid4().hex[:8]}",
                source="redteam_trajectory",
                locator=f"{py_file}:{func_name}",
                raw={
                    "mode": "live",
                    "payload_id": payload["id"],
                    "payload_name": payload["name"],
                    "function": func_name,
                    "vector": payload["vector"],
                    "status": status,
                    "exception_type": outcome.get("exception_type"),
                    "payload_preview": payload["payload"][:100],
                },
            )
            trajectory_evidence.append(ev)

    summary = {
        "target": target_path,
        "total_invocations": len(combos),
        "live_confirmed": live_confirmed,
        "results": results,
        "trajectory_evidence": [ev.model_dump() for ev in trajectory_evidence],
    }

    print(f"\n[LiveRedTeam] {live_confirmed}/{len(combos)} invocations live-confirmed")
    print("-" * 50)
    return summary
