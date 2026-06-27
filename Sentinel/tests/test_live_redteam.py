"""
Tests for the live (sandboxed) red team runner.

These exercise real subprocess execution, so they're slower than the
rest of the suite — but they're the proof that the sandbox model
(disposable cwd, network kill-switch, path-like-param exclusion,
allow-list) actually holds, not just that it's documented.
"""
from pathlib import Path

from sentinel.redteam.live_runner import run_live_red_team, _discover_callable_targets

T1_PATH = str(Path(__file__).parent.parent / "targets" / "t1_injection")
T5_PATH = str(Path(__file__).parent.parent / "targets" / "t5_deserial")
C1_PATH = str(Path(__file__).parent.parent / "targets" / "c1_clean")


def test_t1_payloads_live_confirmed():
    """T1's eval()/subprocess gadgets must actually fire when called live."""
    summary = run_live_red_team(T1_PATH)
    assert summary["total_invocations"] > 0
    assert summary["live_confirmed"] == summary["total_invocations"]
    assert len(summary["trajectory_evidence"]) == summary["live_confirmed"]
    for ev in summary["trajectory_evidence"]:
        assert ev["raw"]["mode"] == "live"


def test_clean_target_has_no_live_invocations():
    """C1 has no functions matching the str/bytes-first-param criteria."""
    summary = run_live_red_team(C1_PATH)
    assert summary["total_invocations"] == 0
    assert summary["live_confirmed"] == 0
    assert summary["trajectory_evidence"] == []


def test_path_like_parameters_are_never_called_with_raw_payload():
    """
    T5's run_cleanup(temp_dir: str) must be excluded from discovery —
    its first param name contains "dir", which is exactly the filesystem-
    path exclusion this sandbox model depends on.
    """
    callables = _discover_callable_targets(Path(T5_PATH) / "agent.py")
    names = [name for name, _ in callables]
    assert "run_cleanup" not in names
    assert "load_agent_state" in names  # bytes param, name is safe — should match


def test_live_red_team_blocks_path_traversal():
    """A target_path outside the scan root must be rejected, not executed."""
    summary = run_live_red_team("../../../../Windows/System32")
    assert summary["total_invocations"] == 0
    assert "blocked_reason" in summary


def test_live_invocation_does_not_leave_files_in_repo():
    """
    The sandbox's disposable cwd must contain any file writes the target
    code performs — nothing should land in the real targets/ directory.
    """
    target_dir = Path(T1_PATH)
    before = set(target_dir.rglob("*"))
    run_live_red_team(T1_PATH)
    after = set(target_dir.rglob("*")) - {target_dir / "__pycache__"}
    after = {p for p in after if "__pycache__" not in p.parts}
    before = {p for p in before if "__pycache__" not in p.parts}
    assert after == before
