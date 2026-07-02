# src/routepanel/syncd/resolver.py
from typing import Iterable
import asyncio
import dns.asyncresolver


async def resolve_domain(domain: str, nameserver: str | None = None, port: int = 53) -> set[str]:
    ips: set[str] = set()
    try:
        resolver = dns.asyncresolver.Resolver()
        if nameserver:
            resolver.nameservers = [nameserver]
            resolver.port = port
        answer = await resolver.resolve(domain, "A")
        for rdata in answer:
            ips.add(str(rdata))
    except Exception:
        pass
    return ips


async def resolve_domains(domains: Iterable[str], nameserver: str | None = None, port: int = 53) -> set[str]:
    tasks = [resolve_domain(d, nameserver, port) for d in domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_ips: set[str] = set()
    for r in results:
        if isinstance(r, set):
            all_ips |= r
    return all_ips
