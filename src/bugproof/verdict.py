"""The deterministic verdict function.

Pure, deterministic, no LLM call. A candidate test is VALID for a case iff
all five conditions in BUGPROOF_AGENT_BRIEF.md section 4 hold. Each failed
condition produces exactly one of the five named rejection reasons -- that
vocabulary is what the failure taxonomy and the repair loop are built on,
so the reason strings below are load-bearing and must not be renamed
casually.

Subprocess budget per candidate: conditions 4 and 5 (passes on fixed; no
regression) used to cost two separate pytest runs each keyed off a third
"does the native suite pass on its own" run repeated for every candidate,
for four pytest subprocesses total. The third run's result cannot change
across candidates -- it depends only on fixed/, which is immutable
benchmark data -- so it is now a corpus-level invariant, checked once via
verify_fixed_suite_baseline(), not per candidate. Conditions 4 and 5 are
now proven together by a single combined run (native suite + candidate),
read back through structured JUnit classnames rather than string
heuristics: the candidate's own testcases (classname == the candidate
file's stem) answer condition 4; any *other* testcase failing answers
condition 5, because the baseline check already proved those tests pass
without the candidate present. Two pytest subprocesses per candidate
instead of four.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bugproof.sandbox import SandboxRun, TestCaseResult, run_pytest

COLLECTION_ERROR = "COLLECTION_ERROR"
PASSES_ON_BUGGY = "PASSES_ON_BUGGY"
WRONG_SYMPTOM = "WRONG_SYMPTOM"
FAILS_ON_FIXED = "FAILS_ON_FIXED"
SUITE_REGRESSION = "SUITE_REGRESSION"

REASONS = (
    COLLECTION_ERROR,
    PASSES_ON_BUGGY,
    WRONG_SYMPTOM,
    FAILS_ON_FIXED,
    SUITE_REGRESSION,
)

# Not one of the five oracle reasons above. A timeout means the sandbox
# could not determine any of those five conditions within its time budget
# (e.g. a candidate test that hangs) -- it is a harness-level failure, not
# a claim about the candidate's correctness, and must stay distinguishable
# from an ordinary REJECTED verdict so nothing downstream mistakes "we
# don't know" for "we know it's wrong."
TIMEOUT = "TIMEOUT"


@dataclass
class Oracle:
    case_id: str
    difficulty: str
    failure_family: str
    exception_type: str
    message_pattern: str
    description: str
    decoy_expected_reason: str = ""


@dataclass
class Verdict:
    status: str  # "VALID", "REJECTED", or "ERROR" (harness-level, see TIMEOUT)
    reason: str | None
    detail: str
    buggy_run: SandboxRun | None = None
    fixed_run: SandboxRun | None = None

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID"


@dataclass
class FixedSuiteBaseline:
    """Result of validating one case's fixed/ native suite on its own.

    This is a corpus-validation invariant, not a per-candidate check: run
    once per case, before any candidate is evaluated against it. If it
    fails, the case is broken benchmark data -- fix it or drop it, don't
    evaluate candidates against it.
    """

    case_id: str
    ok: bool
    detail: str
    run: SandboxRun | None = None


def load_oracle(case_dir: Path) -> Oracle:
    """Parse oracle.yaml.

    This is a hand-rolled parser for BugProof's own restricted schema --
    flat ``key: value`` lines, one per line, optional quoting, ``#``
    comments. It is not a general YAML parser and must not be treated as
    one; the schema is deliberately kept flat so this stays honest.
    """
    path = Path(case_dir) / "oracle.yaml"
    raw = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        raw[key] = value

    return Oracle(
        case_id=raw.get("case_id", ""),
        difficulty=raw.get("difficulty", ""),
        failure_family=raw.get("failure_family", ""),
        exception_type=raw.get("exception_type", ""),
        message_pattern=raw.get("message_pattern", ""),
        description=raw.get("description", ""),
        decoy_expected_reason=raw.get("decoy_expected_reason", ""),
    )


def _symptom_matches(run: SandboxRun, oracle: Oracle) -> bool:
    haystack = run.failure_text() + "\n" + run.stdout + "\n" + run.stderr

    if oracle.exception_type and oracle.exception_type not in haystack:
        return False

    if oracle.message_pattern and not re.search(oracle.message_pattern, haystack):
        return False

    # A symptom check with nothing configured cannot discriminate anything,
    # which would make WRONG_SYMPTOM unreachable -- that's a broken oracle,
    # not a passing one.
    if not oracle.exception_type and not oracle.message_pattern:
        raise ValueError(
            f"oracle for {oracle.case_id!r} sets neither exception_type nor "
            "message_pattern -- symptom matching would be a no-op"
        )

    return True


def verify_fixed_suite_baseline(case_dir: Path) -> FixedSuiteBaseline:
    """Prove fixed/'s own native test suite collects and passes alone.

    Called once per case, not once per candidate: the result cannot change
    across candidates because it depends only on fixed/, which is
    immutable. evaluate() relies on this having already been proven true
    -- if a native-suite testcase fails inside a combined (native suite +
    candidate) run, evaluate() attributes that failure to the candidate
    (SUITE_REGRESSION) without re-checking whether the native suite was
    already broken on its own. If this check fails, that attribution is
    unsound and the case is not valid benchmark data.
    """
    case_dir = Path(case_dir)
    fixed_dir = case_dir / "fixed"
    tests_dir = fixed_dir / "tests"
    case_id = case_dir.name

    if not tests_dir.exists():
        return FixedSuiteBaseline(case_id=case_id, ok=True, detail="no native suite to validate")

    run = run_pytest(fixed_dir, test_files=[], test_targets=["tests"])

    if run.timed_out:
        return FixedSuiteBaseline(case_id=case_id, ok=False, detail="fixed/tests timed out", run=run)
    if run.collection_error:
        return FixedSuiteBaseline(case_id=case_id, ok=False, detail=run.collection_error_text[:2000], run=run)
    if run.any_failed():
        return FixedSuiteBaseline(case_id=case_id, ok=False, detail=run.failure_text()[:2000], run=run)
    return FixedSuiteBaseline(
        case_id=case_id, ok=True, detail=f"{len(run.passing())} native test(s) passed", run=run
    )


def _is_candidate_testcase(tc: TestCaseResult, candidate_test_path: Path) -> bool:
    """True if a JUnit testcase came from the candidate file, not the native suite.

    Structural, not a string heuristic: the candidate file is copied to the
    sandbox root, so pytest's classname for its tests is exactly the
    file's stem (e.g. "reference_test"); native-suite tests live under
    tests/, so pytest classnames them "tests.<module>". Verified against
    real JUnit output, not assumed.
    """
    return tc.classname == candidate_test_path.stem


def evaluate(case_dir: Path, candidate_test_path: Path) -> Verdict:
    """Run the five-condition gate for one candidate test against one case.

    Two pytest subprocesses for a normal VALID candidate: one against
    buggy/ (conditions 1-3), one against fixed/ with the native suite
    alongside the candidate (conditions 4 and 5 together). See the module
    docstring for why this is sound.
    """
    case_dir = Path(case_dir)
    candidate_test_path = Path(candidate_test_path)
    oracle = load_oracle(case_dir)

    buggy_dir = case_dir / "buggy"
    fixed_dir = case_dir / "fixed"

    # 1 & 2: collects and fails on buggy.
    buggy_run = run_pytest(buggy_dir, test_files=[candidate_test_path])

    if buggy_run.timed_out:
        return Verdict(
            status="ERROR",
            reason=TIMEOUT,
            detail="candidate test did not finish running against buggy/ within the time budget",
            buggy_run=buggy_run,
        )

    if buggy_run.collection_error:
        return Verdict(
            status="REJECTED",
            reason=COLLECTION_ERROR,
            detail=buggy_run.collection_error_text[:2000],
            buggy_run=buggy_run,
        )

    if not buggy_run.any_failed():
        return Verdict(
            status="REJECTED",
            reason=PASSES_ON_BUGGY,
            detail="candidate test collected and passed on buggy/ -- no failure to reproduce",
            buggy_run=buggy_run,
        )

    # 3: fails for the reported reason.
    if not _symptom_matches(buggy_run, oracle):
        return Verdict(
            status="REJECTED",
            reason=WRONG_SYMPTOM,
            detail=(
                f"expected exception_type={oracle.exception_type!r} "
                f"message_pattern={oracle.message_pattern!r}; "
                f"observed failure text did not match"
            ),
            buggy_run=buggy_run,
        )

    # 4 & 5 together: does the candidate pass on fixed/, and does adding it
    # break any test that fixed/'s own native suite already had passing?
    # One pytest invocation answers both, provided the native suite's
    # standalone result is already known -- see verify_fixed_suite_baseline.
    has_native_suite = (fixed_dir / "tests").exists()
    targets = (["tests"] if has_native_suite else []) + [candidate_test_path.name]
    combined_run = run_pytest(fixed_dir, test_files=[candidate_test_path], test_targets=targets)

    if combined_run.timed_out:
        return Verdict(
            status="ERROR",
            reason=TIMEOUT,
            detail="candidate test did not finish running against fixed/ within the time budget",
            buggy_run=buggy_run,
            fixed_run=combined_run,
        )

    if combined_run.collection_error:
        return Verdict(
            status="REJECTED",
            reason=FAILS_ON_FIXED,
            detail=combined_run.collection_error_text[:2000],
            buggy_run=buggy_run,
            fixed_run=combined_run,
        )

    candidate_testcases = [
        tc for tc in combined_run.testcases if _is_candidate_testcase(tc, candidate_test_path)
    ]
    native_testcases = [
        tc for tc in combined_run.testcases if not _is_candidate_testcase(tc, candidate_test_path)
    ]

    candidate_failed = [tc for tc in candidate_testcases if tc.status in ("failed", "error")]
    if candidate_failed or not candidate_testcases:
        detail = "\n".join(tc.text or tc.message for tc in candidate_failed)
        if not detail:
            detail = "candidate produced no matching testcase in the combined run against fixed/"
        return Verdict(
            status="REJECTED",
            reason=FAILS_ON_FIXED,
            detail=detail[:2000],
            buggy_run=buggy_run,
            fixed_run=combined_run,
        )

    native_failed = [tc for tc in native_testcases if tc.status in ("failed", "error")]
    if native_failed:
        detail = (
            "previously-passing native test(s) now fail with the candidate present: "
            f"{[tc.nodeid for tc in native_failed]}"
        )
        return Verdict(
            status="REJECTED",
            reason=SUITE_REGRESSION,
            detail=detail[:2000],
            buggy_run=buggy_run,
            fixed_run=combined_run,
        )

    return Verdict(
        status="VALID",
        reason=None,
        detail="all five conditions satisfied",
        buggy_run=buggy_run,
        fixed_run=combined_run,
    )
