"""Isolated pytest execution.

Two things happen here and they must not be confused:

- ``create_agent_workspace`` builds the directory an agent is allowed to see:
  only ``report.md`` and the contents of ``buggy/``. This is enforced here,
  by copying exactly those paths, rather than trusted to prompt wording.
- ``run_pytest`` executes a candidate test file against a project directory
  (``buggy/`` or ``fixed/``) in a throwaway copy, so a candidate test can
  never write into the case's source-of-truth files. It is used by
  ``verdict.py`` and by the harness self-test, which are allowed to see
  ``fixed/`` because they hold the oracle -- the agent under test is not.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 30

# Bound on draining a killed process's output. See the comment on the
# communicate() call after proc.kill() in run_pytest: killing the direct
# child does not guarantee its pipes close, if some descendant inherited
# the handles and is still alive. Without this second bound, that case
# turns a 30s configured timeout into an unbounded hang.
POST_KILL_DRAIN_SECONDS = 10

# Opt-in tracing for diagnosing sandbox lifecycle issues (intermittent
# non-termination, hangs) without touching normal output. Off by default;
# set BUGPROOF_TRACE=1 to get one line per lifecycle event to stderr:
# case id, revision (buggy/fixed), candidate type (reference/decoy/
# regression-baseline), the pytest subprocess's PID once known, and
# monotonic elapsed time since this process started. Left in place
# deliberately -- if an intermittent stall recurs, this is what lets it be
# pinned to an exact case/revision/candidate and an exact PID to inspect
# live, rather than re-instrumenting from scratch.
_TRACE = os.environ.get("BUGPROOF_TRACE") == "1"
_TRACE_T0 = time.monotonic()


def _trace(event: str, **fields: object) -> None:
    if not _TRACE:
        return
    elapsed = time.monotonic() - _TRACE_T0
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"[TRACE {elapsed:8.3f}s pid={os.getpid()}] {event} {detail}", file=sys.stderr, flush=True)


@dataclass
class TestCaseResult:
    classname: str
    name: str
    status: str  # "passed" | "failed" | "error" | "skipped"
    message: str = ""
    text: str = ""

    @property
    def nodeid(self) -> str:
        return f"{self.classname}::{self.name}"


@dataclass
class SandboxRun:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    collection_error: bool
    collection_error_text: str
    testcases: list[TestCaseResult] = field(default_factory=list)

    def failing(self) -> list[TestCaseResult]:
        return [tc for tc in self.testcases if tc.status in ("failed", "error")]

    def passing(self) -> list[TestCaseResult]:
        return [tc for tc in self.testcases if tc.status == "passed"]

    def any_failed(self) -> bool:
        return len(self.failing()) > 0

    def failure_text(self) -> str:
        """Concatenated failure/error text, used for symptom matching."""
        parts = [tc.text or tc.message for tc in self.failing()]
        return "\n".join(parts)


def create_agent_workspace(case_dir: Path, dest_dir: Path) -> Path:
    """Copy only the paths an agent is permitted to see into dest_dir.

    Permitted: report.md and the full contents of buggy/. Everything else
    in the case directory (fixed/, oracle.yaml, reference_test.py,
    decoy_test.py) is withheld.
    """
    case_dir = Path(case_dir)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    report = case_dir / "report.md"
    if report.exists():
        shutil.copy2(report, dest_dir / "report.md")

    buggy = case_dir / "buggy"
    if buggy.exists():
        shutil.copytree(buggy, dest_dir / "buggy", dirs_exist_ok=True)

    return dest_dir


def run_pytest(
    project_dir: Path,
    test_files: list[Path] | None = None,
    test_targets: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SandboxRun:
    """Run pytest against a copy of project_dir, isolated in a temp dir.

    project_dir is copied wholesale into a scratch directory so nothing a
    candidate test does (writes, mutates fixtures) touches the real case
    files. test_files are extra files (e.g. a candidate test) copied into
    the scratch root alongside the project before running. test_targets
    restricts which paths pytest actually collects (default: everything
    copied in, i.e. project contents plus the copied-in test files).
    """
    project_dir = Path(project_dir)
    test_files = test_files or []

    # Context for tracing only -- derived from paths already on hand, no
    # new parameters, no behavior change when BUGPROOF_TRACE is unset.
    case_id = project_dir.parent.name if project_dir.name in ("buggy", "fixed") else project_dir.name
    revision = project_dir.name if project_dir.name in ("buggy", "fixed") else "?"
    candidate_type = "regression-baseline"
    for tf in test_files:
        stem = Path(tf).stem
        if "reference" in stem:
            candidate_type = "reference"
        elif "decoy" in stem:
            candidate_type = "decoy"
        else:
            candidate_type = stem

    _trace("BEGIN", case=case_id, revision=revision, candidate=candidate_type)

    workdir = Path(tempfile.mkdtemp(prefix="bugproof_sandbox_"))
    try:
        if project_dir.exists():
            shutil.copytree(project_dir, workdir, dirs_exist_ok=True)

        copied_names: list[str] = []
        for tf in test_files:
            tf = Path(tf)
            dest = workdir / tf.name
            shutil.copy2(tf, dest)
            copied_names.append(tf.name)

        junit_path = workdir / "_bugproof_junit.xml"
        targets = test_targets if test_targets is not None else copied_names

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit_path}",
        ]

        # The sandbox must behave the same regardless of what happens to be
        # pip-installed globally on the host running it. Without this,
        # pytest autoloads every third-party plugin registered on the
        # machine (measured here: anyio, dash's Selenium-backed testing
        # plugin, langsmith, pytest-asyncio, pytest-cov, hypothesis) via
        # setuptools entry points -- none of which BugProof depends on.
        # That cost ~4.2s of import overhead per invocation in testing
        # (vs ~0.5s with autoload off), and it compounds: a single
        # harness_selftest run makes ~15 of these calls sequentially, so
        # the run time -- and, since some of those plugins do their own
        # I/O at import/collection time, the run's *reliability* -- was
        # entirely a function of whatever else was installed on this
        # machine. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 is pytest's own
        # mechanism for exactly this: only pytest's built-in plugins load,
        # so the sandbox is deterministic across machines.
        env = dict(os.environ)
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        # subprocess.Popen instead of the subprocess.run() convenience
        # wrapper for one reason only: it hands back the child's PID the
        # moment it's spawned, before we wait on it -- run() only gives you
        # a PID after the call already returned. Same subprocess, same
        # single call, no added process/thread/worker.
        timed_out = False
        proc = subprocess.Popen(
            cmd,
            cwd=workdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _trace("SPAWNED", case=case_id, revision=revision, candidate=candidate_type, pytest_pid=proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode
            _trace(
                "COMPLETE",
                case=case_id, revision=revision, candidate=candidate_type,
                pytest_pid=proc.pid, returncode=returncode,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            _trace(
                "TIMEOUT_FIRING",
                case=case_id, revision=revision, candidate=candidate_type, pytest_pid=proc.pid,
            )
            proc.kill()
            # Killing the direct child does not guarantee its stdout/stderr
            # pipes close: if some descendant process inherited those
            # handles and is still alive, communicate() here would block
            # waiting for EOF that never comes, turning a bounded timeout
            # into an unbounded hang. Bound the drain too, and if it's
            # still blocked past that second bound, give up on stdout/
            # stderr for this run rather than hang -- the run is already
            # being reported as timed out either way.
            try:
                stdout, stderr = proc.communicate(timeout=POST_KILL_DRAIN_SECONDS)
                _trace("POST_KILL_DRAIN_OK", case=case_id, pytest_pid=proc.pid)
            except subprocess.TimeoutExpired:
                _trace("POST_KILL_DRAIN_STILL_BLOCKED", case=case_id, pytest_pid=proc.pid)
                stdout, stderr = "", ""
            returncode = -1

        _trace("END", case=case_id, revision=revision, candidate=candidate_type)
        return _parse_run(junit_path, stdout or "", stderr or "", returncode, timed_out)
    finally:
        # No synchronous shutil.rmtree() here -- this was the proven cause
        # of the intermittent multi-minute stall reproduced on 2026-08-29:
        # a pytest run completed cleanly (process exited, output drained,
        # junit.xml parsed and traced) and the very next thing to run --
        # this cleanup, the only untraced operation before the next
        # BEGIN -- blocked for minutes with the parent fully idle (0.0s
        # CPU progress across repeated samples) and zero child or
        # grandchild processes anywhere in the tree. Windows can hold a
        # just-written file open briefly after its writer exits
        # (observed correlating with antivirus real-time scanning of
        # newly-created files), and rmtree's per-file unlink() blocks on
        # that even with ignore_errors=True, because the block happens
        # inside the OS call itself, before rmtree gets a chance to catch
        # anything. A rename is a single filesystem metadata operation
        # that doesn't open or unlink individual files, so it isn't
        # exposed to that per-file lock. These directories are small
        # (a handful of copied .py files plus one junit.xml); actual
        # deletion happens via the separate, explicit `python -m
        # bugproof.cleanup` (or `make clean`) command -- never automatically
        # as part of evaluation, see sweep_scratch_directories() below --
        # and via the OS's own temp-directory reaping regardless.
        _trace("CLEANUP_START", case=case_id, revision=revision, candidate=candidate_type)
        try:
            workdir.rename(workdir.with_name("done_" + workdir.name))
        except OSError:
            pass  # best-effort; leaving it in place is safe, just untidy
        _trace("CLEANUP_DONE", case=case_id, revision=revision, candidate=candidate_type)


def _parse_run(
    junit_path: Path, stdout: str, stderr: str, returncode: int, timed_out: bool
) -> SandboxRun:
    if timed_out:
        return SandboxRun(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            collection_error=False,
            collection_error_text="timed out",
            testcases=[],
        )

    if not junit_path.exists():
        # pytest never produced a report at all -- e.g. it couldn't even
        # start, or the whole run errored before junitxml was written.
        return SandboxRun(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            collection_error=True,
            collection_error_text=(stdout + "\n" + stderr).strip(),
            testcases=[],
        )

    tree = ET.parse(junit_path)
    root = tree.getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root

    testcases: list[TestCaseResult] = []
    collection_error = False
    collection_error_text = ""

    for tc_el in suite.findall("testcase"):
        classname = tc_el.get("classname", "")
        name = tc_el.get("name", "")
        error_el = tc_el.find("error")
        failure_el = tc_el.find("failure")
        skipped_el = tc_el.find("skipped")

        if error_el is not None:
            status = "error"
            message = error_el.get("message", "")
            text = error_el.text or ""
            # pytest reports collection failures as an <error> testcase
            # whose name is the special "erroring collector" marker.
            if name in ("", "erroring collector") or classname == "":
                collection_error = True
                collection_error_text = text or message
        elif failure_el is not None:
            status = "failed"
            message = failure_el.get("message", "")
            text = failure_el.text or ""
        elif skipped_el is not None:
            status = "skipped"
            message = skipped_el.get("message", "")
            text = skipped_el.text or ""
        else:
            status = "passed"
            message = ""
            text = ""

        testcases.append(
            TestCaseResult(
                classname=classname,
                name=name,
                status=status,
                message=message,
                text=text,
            )
        )

    if not testcases and int(suite.get("errors", "0")) > 0:
        collection_error = True
        collection_error_text = collection_error_text or (stdout + "\n" + stderr).strip()

    return SandboxRun(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        collection_error=collection_error,
        collection_error_text=collection_error_text,
        testcases=testcases,
    )


def sweep_scratch_directories() -> int:
    """Delete every finished sandbox scratch directory. Returns the count removed.

    run_pytest() renames its scratch dir instead of deleting it, on purpose
    -- see the comment in run_pytest's cleanup. That means these
    directories (small: a handful of .py files plus one junit.xml each)
    accumulate under the OS temp dir and need sweeping somewhere -- but
    NOT here, meaning not automatically, and not from anything the
    evaluator runs on its own.

    This was previously called once at the end of harness_selftest.py's
    main(), on the theory that a slow rmtree there would only delay
    process exit after every verdict was already decided and printed. That
    theory was wrong in the way that matters: a judge running
    `python eval/harness_selftest.py` is waiting for the *process* to
    return, not for stdout to stop changing. An unbounded rmtree between
    "the harness is done" and "the process actually exits" is the same
    failure mode the rename-instead-of-delete change was meant to remove,
    just moved to a different line. It has been removed from that call
    site entirely.

    The only caller now is `bugproof.cleanup` (run via `python -m
    bugproof.cleanup` or `make clean`) -- an explicit, separately-invoked
    maintenance command that nothing in evaluation depends on running.
    No thread, process, or timeout wraps this call; ignore_errors=True is
    the only guard, matching the constraint that cleanup stays simple.
    That is acceptable for a command the user chooses to run, in a way it
    is not for something bundled into evaluating a candidate.
    """
    workdir_root = Path(tempfile.gettempdir())
    removed = 0
    for pattern in ("done_bugproof_sandbox_*", "bugproof_sandbox_*"):
        for scratch_dir in workdir_root.glob(pattern):
            shutil.rmtree(scratch_dir, ignore_errors=True)
            removed += 1
    return removed
