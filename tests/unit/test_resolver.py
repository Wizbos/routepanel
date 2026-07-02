# tests/unit/test_resolver.py
import pytest
from unittest.mock import patch, AsyncMock
from routepanel.syncd.resolver import resolve_domain, resolve_domains

@pytest.mark.asyncio
async def test_resolve_domain_returns_ips():
    mock_answer = [type("R", (), {"__str__": lambda s: "1.2.3.4"})()]
    with patch("dns.asyncresolver.Resolver.resolve", new_callable=AsyncMock) as mock_res:
        mock_res.return_value = mock_answer
        result = await resolve_domain("example.com")
    assert "1.2.3.4" in result

@pytest.mark.asyncio
async def test_resolve_domain_returns_empty_on_error():
    with patch("dns.asyncresolver.Resolver.resolve", side_effect=Exception("no DNS")):
        result = await resolve_domain("invalid.invalid")
    assert result == set()

@pytest.mark.asyncio
async def test_resolve_domains_merges():
    async def fake_resolve(domain, *args, **kwargs):  # absorb nameserver/port
        return {"1.1.1.1"} if domain == "a.com" else {"2.2.2.2"}
    with patch("routepanel.syncd.resolver.resolve_domain", side_effect=fake_resolve):
        result = await resolve_domains(["a.com", "b.com"])
    assert result == {"1.1.1.1", "2.2.2.2"}


import dns.asyncresolver
from routepanel.syncd import resolver as resolver_mod


@pytest.mark.asyncio
async def test_resolve_domain_uses_given_nameserver(monkeypatch):
    captured = {}

    class FakeAnswer:
        def __iter__(self):
            return iter([type("R", (), {"__str__": lambda s: "203.0.113.7"})()])

    class FakeResolver:
        def __init__(self):
            self.nameservers = []
            self.port = 53
        async def resolve(self, domain, rdtype):
            captured["ns"] = list(self.nameservers)
            captured["port"] = self.port
            return FakeAnswer()

    monkeypatch.setattr(dns.asyncresolver, "Resolver", FakeResolver)
    ips = await resolver_mod.resolve_domain("example.com", nameserver="127.0.0.1", port=5353)
    assert ips == {"203.0.113.7"}
    assert captured["ns"] == ["127.0.0.1"]
    assert captured["port"] == 5353
