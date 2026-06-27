"""
Tests for the MCP evidence server tools.
Verifies that deterministic tools return structured evidence.
"""
import pytest
from pathlib import Path
from sentinel.mcp.evidence_server import (
    lint_scan, security_scan, dependency_scan,
    _validate_target, InvalidTargetPath, SCAN_ROOT,
)

TARGETS_DIR = str(Path(__file__).parent.parent / "targets")
T1_PATH = str(Path(__file__).parent.parent / "targets" / "t1_injection")


def test_security_scan_finds_issues_in_t1():
    """Bandit must find eval() and subprocess shell=True in T1."""
    result = security_scan(T1_PATH)
    assert result["tool"] == "bandit"
    assert isinstance(result["findings"], list)
    assert len(result["findings"]) > 0, "Expected bandit to find issues in T1"


def test_security_scan_returns_structured_output():
    """Security scan must always return tool, target, findings keys."""
    result = security_scan(T1_PATH)
    assert "tool" in result
    assert "target" in result
    assert "findings" in result


def test_lint_scan_returns_structured_output():
    """Lint scan must always return tool, target, findings keys."""
    result = lint_scan(T1_PATH)
    assert "tool" in result
    assert "target" in result
    assert "findings" in result


def test_dependency_scan_returns_structured_output():
    """Dependency scan must always return structured output."""
    result = dependency_scan(TARGETS_DIR)
    assert "tool" in result
    assert "vulnerabilities" in result


def test_path_traversal_outside_scan_root_is_rejected():
    """A target_path resolving outside SCAN_ROOT must raise InvalidTargetPath."""
    with pytest.raises(InvalidTargetPath):
        _validate_target("../../../../Windows/System32")


def test_valid_relative_path_resolves_inside_scan_root():
    """A legitimate relative target_path must resolve under SCAN_ROOT."""
    resolved = _validate_target("targets/t1_injection")
    assert SCAN_ROOT in resolved.parents or resolved == SCAN_ROOT


def test_nonexistent_path_is_rejected():
    """A target_path that doesn't exist must raise InvalidTargetPath."""
    with pytest.raises(InvalidTargetPath):
        _validate_target("targets/does_not_exist_xyz")


def test_security_scan_on_traversal_path_returns_error_not_crash():
    """A traversal attempt via the public tool must fail safely, not crash."""
    result = security_scan("../../../../Windows/System32")
    assert result["returncode"] == -1
    assert result["findings"] == []