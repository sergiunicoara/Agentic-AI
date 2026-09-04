"""Regression coverage for the OIDC authorization request."""

import asyncio
from urllib.parse import parse_qs, urlparse

import app.services.oidc_service as oidc_service
from app.config import settings
from app.services.oidc_service import get_authorization_url


def _stub_discovery(monkeypatch):
    async def discovery():
        return {"authorization_endpoint": "https://idp.example.com/authorize"}

    monkeypatch.setattr(oidc_service, "_discovery", discovery)


def test_authorization_url_encodes_every_parameter(monkeypatch):
    _stub_discovery(monkeypatch)
    monkeypatch.setattr(settings, "oidc_redirect_uri", "https://dash.example.com/auth/callback")
    monkeypatch.setattr(settings, "oidc_client_id", "client-1")

    url = asyncio.run(get_authorization_url(state="st", code_challenge="chal"))
    query = parse_qs(urlparse(url).query)

    assert query["redirect_uri"] == ["https://dash.example.com/auth/callback"]
    assert query["scope"] == ["openid email profile"]
    assert "%3A%2F%2F" in url          # the redirect_uri is escaped, not raw
    assert " " not in url


def test_a_hostile_code_challenge_cannot_inject_parameters(monkeypatch):
    """String concatenation let a caller append their own redirect_uri."""
    _stub_discovery(monkeypatch)
    monkeypatch.setattr(settings, "oidc_redirect_uri", "https://dash.example.com/auth/callback")

    hostile = "AAA&redirect_uri=https://evil.example/steal&x="
    url = asyncio.run(get_authorization_url(state="st", code_challenge=hostile))
    query = parse_qs(urlparse(url).query)

    assert query["redirect_uri"] == ["https://dash.example.com/auth/callback"]
    assert query["code_challenge"] == [hostile]
    assert "evil.example" not in urlparse(url).query.replace("%3A%2F%2Fevil", "")


def test_authorize_endpoint_rejects_a_malformed_challenge(client, monkeypatch):
    async def no_rate_limit(*_args, **_kwargs):
        return None

    import app.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "_rate_limit", no_rate_limit)

    r = client.get("/api/v1/auth/authorize?code_challenge=AAA%26redirect_uri%3Dhttps://evil")
    assert r.status_code == 400


def test_authorize_endpoint_accepts_a_valid_challenge(client, monkeypatch):
    async def no_rate_limit(*_args, **_kwargs):
        return None

    class FakeRedis:
        async def set(self, *_args, **_kwargs):
            return True

    async def authorization_url(state, code_challenge):
        return f"https://idp.example.com/authorize?state={state}"

    import app.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "_rate_limit", no_rate_limit)
    monkeypatch.setattr(auth_router, "get_redis", lambda: FakeRedis())
    monkeypatch.setattr(auth_router, "get_authorization_url", authorization_url)

    valid = "a" * 43
    r = client.get(f"/api/v1/auth/authorize?code_challenge={valid}")
    assert r.status_code == 200
    assert r.json()["authorization_url"].startswith("https://idp.example.com/authorize")
