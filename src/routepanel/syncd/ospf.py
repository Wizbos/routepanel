# src/routepanel/syncd/ospf.py
import ipaddress

from routepanel.cidr import normalize_cidr


def uncovered_hosts(ipset_members: set[str], static_cidrs: list[str]) -> list[str]:
    """Bare host IPs from the ipset that no static CIDR already covers, in numeric
    order. Covered hosts are routed by their static prefix anyway, so they must not
    take /32 slots from hosts outside it (e.g. GGC caches in RU ISP networks)."""
    nets = []
    for c in static_cidrs:
        try:
            nets.append(ipaddress.ip_network(normalize_cidr(c)))
        except ValueError:
            pass
    hosts = []
    for m in ipset_members:
        if "/" in m:
            continue
        try:
            ip = ipaddress.ip_address(m)
        except ValueError:
            continue
        if not any(ip in n for n in nets):
            hosts.append(ip)
    return [str(ip) for ip in sorted(hosts)]


def build_ospf_desired(ipset_members: set[str], static_cidrs: list[str], cap: int) -> set[str]:
    """OSPF prefix set for one ospf_distribute rule, derived from the LIVE ipset
    (what clients actually resolved via dnsmasq) plus the rule's static CIDRs.

    ipset hash:net renders a /32 host as a bare IP ("1.2.3.4") and a network as
    "1.2.3.0/24". Static CIDRs are advertised verbatim (uncapped); host IPs not
    covered by them are advertised as /32 and capped at `cap` (LSA-storm guard),
    picked in numeric order for deterministic selection."""
    desired: set[str] = set()
    for c in static_cidrs:
        try:
            desired.add(normalize_cidr(c))
        except ValueError:
            pass
    for ip in uncovered_hosts(ipset_members, static_cidrs)[:cap]:
        desired.add(f"{ip}/32")
    return desired
