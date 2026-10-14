"""Shared test configuration for deterministic scanner integration tests."""

import os
import warnings

import pytest

import sentinel.mcp.evidence_server as evidence_server

# Scanners the pipeline treats as required. If any of the first three can't
# be resolved, scanner-backed tests would only be exercising the
# fail-closed path — abort loudly instead of letting them "pass".
_CORE_SCANNERS = ("bandit", "ruff", "pip-audit")

SEMGREP_AVAILABLE = evidence_server.resolve_scanner("semgrep") is not None

requires_semgrep = pytest.mark.skipif(
    not SEMGREP_AVAILABLE,
    reason="semgrep is not resolvable (not installed, or native Windows where it "
           "doesn't run) — semgrep-backed detection can't be exercised here",
)


@pytest.fixture(scope="session", autouse=True)
def require_scanners():
    """
    Fail the session clearly when core scanners are unresolvable, so the
    suite can never silently pass against an environment where the
    deterministic tools never ran.

    semgrep can't run on native Windows. When it is unresolvable it is
    marked optional for this session via SENTINEL_OPTIONAL_SCANNERS (the
    same explicit operator opt-out production offers), with a visible
    warning; semgrep-specific tests skip via @requires_semgrep. The
    fail-closed tests clear that variable themselves.
    """
    missing = [name for name in _CORE_SCANNERS if evidence_server.resolve_scanner(name) is None]
    if missing:
        pytest.exit(
            f"Required scanners not resolvable: {missing}. Install requirements into "
            f"the interpreter running pytest (e.g. venv/Scripts/python -m pytest).",
            returncode=4,
        )
    previous = os.environ.get("SENTINEL_OPTIONAL_SCANNERS")
    if not SEMGREP_AVAILABLE:
        warnings.warn(
            "semgrep not resolvable: SENTINEL_OPTIONAL_SCANNERS=semgrep for this "
            "test session; semgrep-backed tests are skipped",
            stacklevel=1,
        )
        os.environ["SENTINEL_OPTIONAL_SCANNERS"] = "semgrep"
    yield
    if previous is None:
        os.environ.pop("SENTINEL_OPTIONAL_SCANNERS", None)
    else:
        os.environ["SENTINEL_OPTIONAL_SCANNERS"] = previous


@pytest.fixture(autouse=True)
def use_local_semgrep_rules_in_tests(monkeypatch):
    """Keep tests offline while production retains best-effort registry packs."""
    monkeypatch.setattr(
        evidence_server,
        "SEMGREP_CONFIG_GROUPS",
        [[str(evidence_server._SEMGREP_RULES_DIR)]],
    )
    monkeypatch.setattr(evidence_server, "_registry_failed_at", None)
