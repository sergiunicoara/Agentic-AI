"""
Tests proving semgrep genuinely raises Sentinel's detection ceiling beyond
bandit — not just duplicating it. T6 (targets/t6_ssrf) is constructed so
bandit finds nothing relevant to the seeded vulnerabilities at all; only
semgrep's project-authored rules (sentinel/mcp/semgrep_rules/agent_security.yaml)
catch them. If these tests fail, the "semgrep raises the ceiling" claim in
the README is no longer backed by anything.
"""
import json
from pathlib import Path
from unittest.mock import patch

import sentinel.mcp.evidence_server as evidence_server
from sentinel.mcp.evidence_server import security_scan, semgrep_scan
from sentinel.pipeline import run_sentinel
from conftest import requires_semgrep

T6_PATH = str(Path(__file__).parent.parent / "targets" / "t6_ssrf")


def test_registry_pack_configuration_is_present():
    """Production keeps the broader, best-effort registry packs enabled."""
    assert evidence_server._REGISTRY_CONFIG_GROUP == ["p/python", "p/gitleaks"]


def test_bandit_finds_nothing_relevant_on_t6():
    """
    Bandit must NOT catch the SSRF or the API-key-by-value-format issue —
    this is the whole point of T6. (It may still flag unrelated style
    things like missing request timeouts; that's fine.)
    """
    result = security_scan(T6_PATH)
    relevant_test_ids = {"B105", "B106", "B107"}  # the credential-name checks
    findings_test_ids = {f.get("test_id") for f in result["findings"]}
    assert not (findings_test_ids & relevant_test_ids), (
        "Bandit unexpectedly caught the credential — T6 no longer "
        "demonstrates a bandit blind spot"
    )


@requires_semgrep
def test_semgrep_catches_ssrf_on_t6():
    """The custom sentinel-ssrf-unvalidated-url rule must fire on T6."""
    result = semgrep_scan(T6_PATH)
    check_ids = [f["check_id"] for f in result["findings"]]
    assert any("ssrf" in c.lower() for c in check_ids)


@requires_semgrep
def test_semgrep_catches_llm_key_by_value_format_on_t6():
    """The custom sentinel-llm-api-key-hardcoded rule must fire on T6."""
    result = semgrep_scan(T6_PATH)
    check_ids = [f["check_id"] for f in result["findings"]]
    assert any("llm-api-key" in c.lower() for c in check_ids)


@requires_semgrep
def test_local_rules_survive_a_failed_registry_pack(monkeypatch):
    """
    The local-rules config group runs as its own semgrep invocation
    specifically so that a broken/unreachable registry pack group (no
    network, bad pack name, etc.) doesn't zero out the project's own
    local rules, which need no network at all. This is a regression test
    for that exact failure mode.
    """
    real_run = evidence_server._run

    def fail_fake_registry(command, **kwargs):
        if "p/totally-fake-nonexistent-pack-xyz" in command:
            return {"returncode": -1, "stdout": "", "stderr": "registry unavailable"}
        return real_run(command, **kwargs)

    monkeypatch.setattr(evidence_server, "_run", fail_fake_registry)

    with patch.object(
        evidence_server, "SEMGREP_CONFIG_GROUPS",
        [[str(evidence_server._SEMGREP_RULES_DIR)], ["p/totally-fake-nonexistent-pack-xyz"]],
    ):
        result = semgrep_scan(T6_PATH)

    check_ids = [f["check_id"] for f in result["findings"]]
    assert any("ssrf" in c.lower() for c in check_ids), (
        "Local project rules must still fire even when a registry pack "
        "fails to fetch"
    )


def _fake_semgrep(calls, registry_group, registry_ok=lambda: False):
    def fake_run(command, **_kwargs):
        configs = [
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == "--config"
        ]
        calls.append(configs)
        if configs == registry_group and not registry_ok():
            return {"status": "ran", "returncode": 2, "stdout": "", "stderr": "registry unavailable"}
        return {"status": "ran", "returncode": 0,
                "stdout": '{"results": [], "errors": []}', "stderr": ""}
    return fake_run


def test_failed_registry_pack_backs_off_then_retries(monkeypatch):
    """
    A registry outage must not add a 120-second timeout to every target in
    a batch — but it must not be sticky for the life of the process either:
    after the back-off window the registry group is retried.
    """
    local_group = [str(evidence_server._SEMGREP_RULES_DIR)]
    registry_group = ["p/python", "p/gitleaks"]
    calls = []
    clock = {"now": 1000.0}

    monkeypatch.setattr(evidence_server, "SEMGREP_CONFIG_GROUPS", [local_group, registry_group])
    monkeypatch.setattr(evidence_server, "_REGISTRY_CONFIG_GROUP", registry_group)
    monkeypatch.setattr(evidence_server, "_registry_failed_at", None)
    monkeypatch.setattr(evidence_server, "REGISTRY_RETRY_SECONDS", 300)
    monkeypatch.setattr(evidence_server, "_now", lambda: clock["now"])
    monkeypatch.setattr(evidence_server, "_run", _fake_semgrep(calls, registry_group))

    first = semgrep_scan(T6_PATH)
    second = semgrep_scan(T6_PATH)
    assert calls.count(registry_group) == 1
    assert calls.count(local_group) == 2
    # A registry failure is a warning, not a scan failure: local rules ran.
    assert first["status"] == "ok" and second["status"] == "ok"
    assert any("registry" in w for w in second["warnings"])

    clock["now"] += 301
    semgrep_scan(T6_PATH)
    assert calls.count(registry_group) == 2


def test_semgrep_parse_errors_do_not_discard_results(monkeypatch):
    """One unparseable file must not throw away the whole group's results."""
    payload = json.dumps({
        "results": [{"check_id": "sentinel-ssrf-unvalidated-url", "path": "a.py",
                     "start": {"line": 3}, "extra": {"message": "m"}}],
        "errors": [{"message": "Syntax error in b.py"}],
    })
    monkeypatch.setattr(evidence_server, "_run", lambda *_a, **_k: {
        "status": "ran", "returncode": 2, "stdout": payload, "stderr": ""})
    result = semgrep_scan(T6_PATH)
    assert result["status"] == "ok"
    assert len(result["findings"]) == 1
    assert any("Syntax error" in w for w in result["warnings"])


def test_semgrep_missing_is_reported_not_silently_empty(monkeypatch):
    monkeypatch.setattr(evidence_server, "resolve_scanner", lambda _name: None)
    result = semgrep_scan(T6_PATH)
    assert result["status"] == "missing"
    assert result["findings"] == []


def test_semgrep_runs_with_nosem_disabled(monkeypatch):
    """A target must not be able to silence rules with `# nosemgrep`."""
    seen = []
    monkeypatch.setattr(evidence_server, "_run", lambda cmd, **_k: seen.append(cmd) or {
        "status": "ran", "returncode": 0, "stdout": '{"results": [], "errors": []}', "stderr": ""})
    semgrep_scan(T6_PATH)
    assert seen and all("--disable-nosem" in cmd for cmd in seen)


@requires_semgrep
def test_full_pipeline_catches_t6_via_semgrep_only():
    """
    The end-to-end pipeline must FAIL on T6, and every surviving finding
    must trace to semgrep evidence (evidence_id is prefixed "ev_semgrep_"
    by EvidenceAgent) — proving the detection-ceiling raise holds all the
    way through the Adjudicator gate, not just at the tool level.
    """
    attestation = run_sentinel(T6_PATH, verbose=False)
    assert attestation.verdict == "fail"
    assert len(attestation.findings) > 0

    for finding in attestation.findings:
        assert all(eid.startswith("ev_semgrep_") for eid in finding.evidence_ids), (
            f"Finding '{finding.title}' has a non-semgrep evidence_id — "
            f"T6 should only be caught via semgrep: {finding.evidence_ids}"
        )
