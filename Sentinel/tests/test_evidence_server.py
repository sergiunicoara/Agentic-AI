"""
Tests for the MCP evidence server tools.
Verifies that deterministic tools return structured evidence.
"""
import pytest
from pathlib import Path
from sentinel.mcp.evidence_server import lint_scan, security_scan, dependency_scan

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