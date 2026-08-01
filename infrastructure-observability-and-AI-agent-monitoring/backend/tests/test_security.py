import pytest

from app.config import Settings, settings
from app.services.ingest_auth import valid_emit_key
from app.services.abac import check_span_access


def test_production_rejects_short_secrets():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            environment="production",
            jwt_secret="short",
            frontend_origin="https://dashboard.example.com",
            oidc_redirect_uri="https://dashboard.example.com/auth/callback",
            emit_agent_keys='{"researcher":"x"}',
        )


def test_scoped_ingestion_key_is_bound_to_agent(monkeypatch):
    monkeypatch.setattr(settings, "emit_agent_keys", '{"researcher":"key-a"}')
    monkeypatch.setattr(settings, "emit_api_key", "")

    assert valid_emit_key("key-a", "researcher")
    assert not valid_emit_key("key-a", "writer")


def test_production_rejects_plaintext_browser_origin():
    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        Settings(
            environment="production",
            jwt_secret="x" * 32,
            frontend_origin="http://dashboard.example.com",
            oidc_redirect_uri="https://dashboard.example.com/auth/callback",
            emit_agent_keys='{"researcher":"x' + ("x" * 31) + '"}',
        )


def test_confidential_span_requires_clearance():
    resource = {"data_sensitivity": "confidential", "owner_email": ""}
    assert not check_span_access({"role": "viewer", "clearance_level": 0}, resource)
    assert check_span_access({"role": "admin", "clearance_level": 2}, resource)
