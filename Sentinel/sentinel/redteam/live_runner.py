"""
Live Red Team Runner — actually executes corpus payloads against the
target's real functions, instead of only checking for static surfaces
(sentinel.redteam.runner does the static check; this is the live one).

HARDENING, NOT ISOLATION. There is no container, VM, seccomp profile or
separate user here: target code runs as the same OS user as Sentinel, with
that user's filesystem access. Everything below raises the bar; none of it
is a security boundary. Never point this at untrusted third-party code
without an external sandbox (gVisor, firecracker, a throwaway container).

SAFETY MODEL — read before enabling (opt-in only, never on by default):
- Restricted to targets inside the same allow-list the MCP evidence server
  enforces (SCAN_ROOT in sentinel/mcp/evidence_server.py). This is built
  for the bundled, trusted target corpus — not for scanning arbitrary
  third-party code live.
- Target code is NEVER imported or called in the main Sentinel process.
  Both discovery (which functions exist) and invocation (calling one with
  a payload) happen inside sentinel.redteam._live_worker, in its own
  subprocess, every single time.
- Each subprocess (discovery AND invocation) gets:
    * a fresh, disposable temp directory as its cwd (and TEMP/TMP) —
      relative-path file writes land there, not in the repo, and the
      directory is deleted afterward. Absolute paths are NOT contained.
    * an allow-listed environment: only PATH, PYTHONPATH, TEMP/TMP and the
      Windows spawn essentials are passed — no credentials
      (GOOGLE_APPLICATION_CREDENTIALS, *_KEY, *_TOKEN, CLOUDSDK_*, ...)
    * network sockets patched to raise immediately (an in-process Python
      patch — native extensions or child processes are not covered)
    * dangerous sinks (eval/exec/os.system/subprocess/pickle) guarded: a
      payload reaching one is recorded and refused instead of executed
    * a hard wall-clock timeout that kills the whole process tree
      (process group on POSIX, taskkill /T on Windows)
    * (POSIX only) CPU-time and address-space rlimits
- An invocation is LIVE-CONFIRMED only when the payload was observed
  reaching a dangerous sink (raw["sinks_hit"]). A call that merely
  completed or raised is not evidence of injection.
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
import signal
from pathlib import Path

from sentinel.mcp.evidence_server import _validate_target, InvalidTargetPath
from sentinel.redteam.corpus import get_all_payloads
from sentinel.models.schemas import Evidence

MAX_LIVE_INVOCATIONS = 16
PER_CALL_TIMEOUT = 5  # seconds, wall-clock, enforced by the parent process

# The repo root, so `python -m sentinel.redteam._live_worker` resolves even
# though the worker's cwd is a disposable temp directory, not the repo.
_REPO_ROOT = str(Path(__file__).parent.parent.parent)


# The only variables inherited from the parent environment. Everything else
# (GOOGLE_APPLICATION_CREDENTIALS, *_KEY, *_TOKEN, CLOUDSDK_*, AWS_*, ...)
# is dropped by construction — an allow-list, not a deny-list.
_INHERITED_ENV = ("PATH", "SystemRoot", "SYSTEMROOT", "COMSPEC", "PATHEXT")


def _sandbox_env(work_dir: str | None = None) -> dict:
    """Allow-listed environment: just enough to spawn the interpreter and
    resolve the sentinel package, with temp files redirected to work_dir."""
    env = {k: os.environ[k] for k in _INHERITED_ENV if os.environ.get(k)}
    env["PYTHONPATH"] = _REPO_ROOT
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if work_dir:
        env["TEMP"] = env["TMP"] = env["TMPDIR"] = work_dir
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the worker and every process it spawned."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _run_worker(args: list[str], work_dir: str) -> tuple[str, str]:
    """
    Run the live worker in its own process group with cwd=work_dir and the
    allow-listed env. On timeout the whole tree is killed and
    subprocess.TimeoutExpired is re-raised.
    """
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        [sys.executable, "-m", "sentinel.redteam._live_worker", *args],
        cwd=work_dir, env=_sandbox_env(work_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        **popen_kwargs,
    )
    try:
        return proc.communicate(timeout=PER_CALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise


def _discover_callable_targets(py_file: Path) -> list[tuple[str, str]]:
    """Ask the (sandboxed) worker which functions in py_file are safe to call.

    Fails safe to [] on anything that isn't a well-formed discovery list —
    including the worker's own error path, which prints a JSON *object*
    (e.g. {"status": "worker_error", ...}) on failure. Blindly iterating
    that as if it were the expected list would iterate its dict keys
    (strings) instead, and `tuple("status")` explodes into a 6-character
    tuple — surfacing as a confusing "too many values to unpack" in the
    caller rather than the real failure. Surface the real reason instead.
    """
    # Discovery imports the target module, i.e. runs its top-level code —
    # so it gets the same disposable cwd as an invocation, never the repo.
    work_dir = tempfile.mkdtemp(prefix="sentinel_live_")
    try:
        stdout, stderr = _run_worker(["--discover", str(py_file)], work_dir)
        lines = stdout.strip().splitlines()
        if not lines:
            if stderr:
                print(f"[LiveRedTeam] discover produced no output for {py_file}: {stderr[:300]}")
            return []
        parsed = json.loads(lines[-1])
        if not isinstance(parsed, list):
            print(f"[LiveRedTeam] discover failed for {py_file}: {parsed}")
            return []
        return [
            tuple(x) for x in parsed
            if isinstance(x, list) and len(x) == 2
        ]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, IndexError, OSError):
        return []
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _run_in_sandbox(py_file: Path, func_name: str, param_kind: str, payload: str) -> dict:
    """Spawn the live-worker subprocess for one (function, payload) pair."""
    work_dir = tempfile.mkdtemp(prefix="sentinel_live_")
    try:
        payload_file = Path(work_dir) / "payload.txt"
        payload_file.write_text(payload, encoding="utf-8")

        try:
            stdout, stderr = _run_worker(
                [str(py_file), func_name, param_kind, str(payload_file)], work_dir,
            )
            lines = stdout.strip().splitlines()
            if not lines:
                return {"status": "no_output", "stderr": stderr[:500]}
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
    every invocation where the payload was OBSERVED reaching a dangerous
    sink (eval/exec/os.system/subprocess/pickle — see _live_worker). A call
    that merely completed or raised, timed out, or was network-blocked is
    recorded in results but is not confirmed and produces no evidence.
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
        # Confirmation requires an observed effect: the payload reached a
        # dangerous sink. Completing (or raising) on its own proves nothing.
        sinks_hit = [s for s in outcome.get("sinks_hit", []) if isinstance(s, str)]
        confirmed = bool(sinks_hit)

        results.append({
            "payload_id": payload["id"],
            "name": payload["name"],
            "function": f"{py_file.name}:{func_name}",
            "status": status,
            "network_blocked": outcome.get("network_blocked", False),
            "sinks_hit": sinks_hit,
            "reflected": bool(outcome.get("reflected")),
            "live_confirmed": confirmed,
        })

        if confirmed:
            label = "LIVE-CONFIRMED"
        elif outcome.get("network_blocked"):
            label = "NETWORK-BLOCKED"
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
                    "sinks_hit": sinks_hit,
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
