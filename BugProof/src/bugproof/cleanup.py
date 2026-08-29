"""Explicit, separate maintenance operation: reclaim finished scratch dirs.

Run: python -m bugproof.cleanup

This is never part of evaluating a candidate or running the corpus
self-test -- see the comment in eval/harness_selftest.py's main() for why
that boundary matters. It exists purely so scratch directories under the
OS temp dir don't accumulate forever between runs. Deletion here can be
slow on some machines (see sandbox.py's run_pytest cleanup comment); that
is acceptable for an explicitly-invoked maintenance command in a way it is
not for something the evaluator runs on its own.
"""

from __future__ import annotations

from bugproof.sandbox import sweep_scratch_directories


def main() -> int:
    removed = sweep_scratch_directories()
    print(f"removed {removed} finished sandbox scratch director{'y' if removed == 1 else 'ies'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
