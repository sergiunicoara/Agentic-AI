"""Dedicated regression coverage for the merged condition-4/5 pytest run.

evaluate() used to prove "passes on fixed" and "introduces no regression"
with three separate pytest subprocesses (fixed alone, native suite alone,
native suite + candidate). It now proves both with one combined run,
telling the candidate's own testcases apart from the native suite's by
JUnit classname (candidate files sit at the sandbox root, so pytest
classnames their tests after the file's stem; native-suite files sit under
tests/, so pytest classnames those "tests.<module>"). This is real pytest
execution end to end, not a mock of the classification logic, because the
thing being protected is exactly whether that classname split holds up
against actual JUnit output.
"""

from pathlib import Path

from bugproof.verdict import SUITE_REGRESSION, evaluate


def test_candidate_that_corrupts_shared_state_is_classified_as_suite_regression(tmp_path):
    case_dir = tmp_path / "regression_case"
    buggy_dir = case_dir / "buggy"
    fixed_dir = case_dir / "fixed"
    native_tests_dir = fixed_dir / "tests"
    buggy_dir.mkdir(parents=True)
    fixed_dir.mkdir(parents=True)
    native_tests_dir.mkdir(parents=True)

    # A trivial off-by-one bug the candidate can legitimately reproduce.
    (buggy_dir / "calc.py").write_text("def double(x):\n    return x + x + 1\n")
    (fixed_dir / "calc.py").write_text("def double(x):\n    return x * 2\n")

    # Shared, importable, mutable state that a badly-behaved candidate can
    # corrupt at import time -- corruption that only shows up once the
    # native suite's own test runs in the same pytest process.
    (fixed_dir / "shared.py").write_text('STATE = {"broken": False}\n')
    (buggy_dir / "shared.py").write_text('STATE = {"broken": False}\n')

    (native_tests_dir / "test_shared_native.py").write_text(
        "import shared\n"
        "from calc import double\n\n"
        "def test_shared_state_starts_clean():\n"
        "    assert shared.STATE['broken'] is False\n\n"
        "def test_double_of_three_is_six():\n"
        "    assert double(3) == 6\n"
    )

    (case_dir / "oracle.yaml").write_text(
        "case_id: regression_case\n"
        "difficulty: medium\n"
        "failure_family: silent_incorrect_result\n"
        "exception_type:\n"
        "message_pattern: 11\n"
        "description: synthetic case for the SUITE_REGRESSION classification test\n"
    )

    # Reproduces the real bug correctly (fails on buggy for the right
    # reason, would pass on fixed on its own) but also corrupts shared
    # module state as an import-time side effect with no cleanup -- the
    # kind of candidate the gate exists to catch.
    candidate = case_dir / "candidate_test.py"
    candidate.write_text(
        "import shared\n"
        "shared.STATE['broken'] = True\n\n"
        "from calc import double\n\n"
        "def test_double_of_five_is_ten():\n"
        "    assert double(5) == 10\n"
    )

    result = evaluate(case_dir, candidate)

    assert result.status == "REJECTED"
    assert result.reason == SUITE_REGRESSION
    assert "test_shared_state_starts_clean" in result.detail
    assert "test_double_of_three_is_six" not in result.detail
