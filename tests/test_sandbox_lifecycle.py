"""Regression coverage for the Phase 0 lifecycle defect.

harness_selftest.py ran sequential pytest subprocesses that took ~4.2s each
(vs ~0.5s in isolation) because pytest was autoloading every third-party
plugin pip-installed on the host machine (dash's Selenium-backed testing
plugin, langsmith, pytest-asyncio, pytest-cov, hypothesis, anyio) --
packages BugProof does not depend on. That made repeated sequential runs
slow and host-dependent rather than deterministic. Fixed in sandbox.py by
setting PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 for the sandboxed subprocess.

Auditing the timeout path that guards against this same class of problem
(a candidate that hangs instead of a plugin that's merely slow) turned up
a second, related bug: a timed-out run has no failing testcases, so it was
falling through into PASSES_ON_BUGGY -- an infrastructure failure silently
reported as an ordinary candidate verdict. Fixed in verdict.py by checking
SandboxRun.timed_out before any of the five oracle conditions.

A third, separate bug caused the intermittent (not every run) multi-minute
stalls reported after the plugin-autoload fix landed: traced and reproduced
on 2026-08-29, isolated to shutil.rmtree(workdir, ignore_errors=True) in
run_pytest's cleanup -- a pytest run completed cleanly (traced: process
exited, output drained, junit.xml parsed) and the very next operation, that
rmtree call, blocked for minutes with the process fully idle (0.0s CPU
progress) and zero child/grandchild processes anywhere in the tree.
ignore_errors=True does not help when the block happens inside the OS call
itself. Fixed in sandbox.py by renaming the scratch dir instead of deleting
it in the hot path; actual deletion is deferred to `make clean`.
"""

import time

from bugproof import sandbox, verdict
from bugproof.sandbox import SandboxRun, run_pytest

HANGING_TEST_SOURCE = "def test_x():\n    while True:\n        pass\n"


def test_run_pytest_disables_third_party_plugin_autoload(tmp_path, monkeypatch):
    captured = {}

    class FakePopen:
        pid = 4242

        def __init__(self, cmd, cwd, env, stdout, stderr, text):
            captured["env"] = env

        def communicate(self, timeout=None):
            return "", ""

        @property
        def returncode(self):
            return 0

    monkeypatch.setattr(sandbox.subprocess, "Popen", FakePopen)

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    run_pytest(project_dir, test_files=[])

    assert captured["env"].get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"


def test_hanging_candidate_test_is_killed_within_its_timeout_budget(tmp_path):
    project_dir = tmp_path / "buggy"
    project_dir.mkdir()
    candidate = tmp_path / "candidate_test.py"
    candidate.write_text(HANGING_TEST_SOURCE)

    start = time.monotonic()
    result = run_pytest(project_dir, test_files=[candidate], timeout=3)
    elapsed = time.monotonic() - start

    assert result.timed_out is True
    assert elapsed < 15, f"expected the sandbox to bound the hang near its 3s timeout, took {elapsed:.1f}s"


def test_timed_out_buggy_run_is_reported_as_a_harness_error_not_a_verdict(tmp_path, monkeypatch):
    case_dir = tmp_path / "hanging_case"
    (case_dir / "buggy").mkdir(parents=True)
    (case_dir / "fixed").mkdir(parents=True)
    (case_dir / "oracle.yaml").write_text(
        "case_id: hanging_case\n"
        "difficulty: easy\n"
        "failure_family: hang\n"
        "exception_type:\n"
        "message_pattern: anything\n"
        "description: synthetic case for the timeout regression test\n"
    )
    candidate = case_dir / "candidate_test.py"
    candidate.write_text(HANGING_TEST_SOURCE)

    timed_out_run = SandboxRun(
        returncode=-1,
        stdout="",
        stderr="",
        timed_out=True,
        collection_error=False,
        collection_error_text="",
        testcases=[],
    )
    monkeypatch.setattr(verdict, "run_pytest", lambda *args, **kwargs: timed_out_run)

    result = verdict.evaluate(case_dir, candidate)

    assert result.status == "ERROR"
    assert result.reason == verdict.TIMEOUT


def test_run_pytest_does_not_synchronously_delete_its_scratch_dir(tmp_path, monkeypatch):
    def exploding_rmtree(*args, **kwargs):
        raise AssertionError("shutil.rmtree must not run in the run_pytest hot path")

    monkeypatch.setattr(sandbox.shutil, "rmtree", exploding_rmtree)

    project_dir = tmp_path / "buggy"
    project_dir.mkdir()
    (project_dir / "sample.py").write_text("VALUE = 1\n")
    candidate = tmp_path / "candidate_test.py"
    candidate.write_text("import sample\n\ndef test_value():\n    assert sample.VALUE == 1\n")

    result = run_pytest(project_dir, test_files=[candidate])

    assert result.timed_out is False
    assert result.any_failed() is False
