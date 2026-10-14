"""Attestation signing: HMAC over the content, tamper-evident, honest when unkeyed."""
import pytest

from sentinel.agents.adjudicator import UNSIGNED, adjudicate, verify_attestation


def _attest():
    return adjudicate([], [], "targets/c1_clean")


def test_unsigned_without_key_and_does_not_verify(monkeypatch):
    monkeypatch.delenv("SENTINEL_SIGNING_KEY", raising=False)
    attestation = _attest()
    assert attestation.signature == UNSIGNED
    assert verify_attestation(attestation) is False


def test_signed_attestation_verifies(monkeypatch):
    monkeypatch.setenv("SENTINEL_SIGNING_KEY", "test-key")
    attestation = _attest()
    assert attestation.signature.startswith("hmac-sha256:")
    assert verify_attestation(attestation) is True


def test_tampering_breaks_verification(monkeypatch):
    monkeypatch.setenv("SENTINEL_SIGNING_KEY", "test-key")
    attestation = _attest()
    attestation.verdict = "fail"
    assert verify_attestation(attestation) is False


def test_wrong_key_does_not_verify(monkeypatch):
    monkeypatch.setenv("SENTINEL_SIGNING_KEY", "test-key")
    attestation = _attest()
    monkeypatch.setenv("SENTINEL_SIGNING_KEY", "other-key")
    assert verify_attestation(attestation) is False


def test_verify_accepts_dict_form(monkeypatch):
    monkeypatch.setenv("SENTINEL_SIGNING_KEY", "test-key")
    attestation = _attest()
    assert verify_attestation(attestation.model_dump(mode="json")) is True
