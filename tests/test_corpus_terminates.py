"""Regression coverage for the Phase 1 corpus-scale non-termination report.

The eventual root cause: harness_selftest.py used to call
sweep_scratch_directories() once, after printing every verdict, on the
theory that a slow shutil.rmtree there would only delay process exit after
the real work was done. That doesn't satisfy "the command terminates" --
a caller of `python eval/harness_selftest.py` waits for the process to
return, not for stdout to stop changing. That call has been removed from
the evaluator path entirely; cleanup is now only reachable through the
separately-invoked `python -m bugproof.cleanup` / `make clean`.

This test asserts on subprocess.run()'s returncode, which only comes back
once the child process has actually exited -- so it fails if any future
change reintroduces a deletion (or anything else) between "results
printed" and "process exits", not just if stdout stops appearing.
"""

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Generously above every observed run (28-41s) and far below the reported
# non-termination (180s+) -- wide enough to not flake on a loaded machine,
# tight enough to fail loudly on a real regression rather than hang the
# test suite itself.
BOUND_SECONDS = 120


def test_full_corpus_selftest_terminates_within_a_bounded_time():
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "eval/harness_selftest.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=BOUND_SECONDS,
    )
    elapsed = time.monotonic() - start

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert elapsed < BOUND_SECONDS


def _load_harness_selftest_module():
    spec = importlib.util.spec_from_file_location(
        "harness_selftest", REPO_ROOT / "eval" / "harness_selftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normal_evaluator_execution_never_calls_shutil_rmtree(monkeypatch):
    """The actual defect from this round: cleanup ran automatically inside
    the evaluator's own process, so a slow delete meant the process itself
    didn't return. Proven directly rather than by timing: patch
    shutil.rmtree to explode, run the real entrypoint end to end over the
    whole corpus, and confirm it was never called.
    """
    from bugproof import sandbox

    def exploding_rmtree(*args, **kwargs):
        raise AssertionError("shutil.rmtree must not run during normal evaluator execution")

    monkeypatch.setattr(sandbox.shutil, "rmtree", exploding_rmtree)

    harness = _load_harness_selftest_module()
    exit_code = harness.main()

    assert exit_code == 0
