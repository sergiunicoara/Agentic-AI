"""X-Forwarded-For handling.

The header is attacker-controlled up to the first trusted proxy, so the client
address is counted from the right-hand side of the chain.
"""

from types import SimpleNamespace

from app.config import settings
from app.services.request_context import client_ip


def a_request(xff=None, peer="10.0.0.9"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_client_address_is_read_from_the_end_of_the_chain(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    # nginx appended the browser address, Envoy appended nginx.
    assert client_ip(a_request("203.0.113.5, 172.18.0.4")) == "203.0.113.5"


def test_a_spoofed_prefix_cannot_win(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    # The caller sent "1.2.3.4"; the chain appended the real values after it.
    assert client_ip(a_request("1.2.3.4, 203.0.113.5, 172.18.0.4")) == "203.0.113.5"


def test_a_short_chain_falls_back_to_the_socket_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    assert client_ip(a_request("1.2.3.4")) == "10.0.0.9"
    assert client_ip(a_request(None)) == "10.0.0.9"


def test_zero_hops_ignores_the_header_entirely(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert client_ip(a_request("1.2.3.4, 203.0.113.5")) == "10.0.0.9"
