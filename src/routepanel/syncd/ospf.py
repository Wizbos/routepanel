# src/routepanel/syncd/ospf.py
from routepanel.cidr import normalize_cidr


def build_ospf_desired(ipset_members: set[str], static_cidrs: list[str], cap: int) -> set[str]:
    """OSPF prefix set for one ospf_distribute rule, derived from the LIVE ipset
    (what clients actually resolved via dnsmasq) plus the rule's static CIDRs.

    ipset hash:net renders a /32 host as a bare IP ("1.2.3.4") and a network as
    "1.2.3.0/24". Static CIDRs are advertised verbatim (uncapped); host IPs are
    advertised as /32 and capped at `cap` (LSA-storm guard) for deterministic
    selection regardless of set iteration order."""
    desired: set[str] = set()
    for c in static_cidrs:
        try:
            desired.add(normalize_cidr(c))
        except ValueError:
            pass
    hosts = sorted(m for m in ipset_members if "/" not in m)
    for ip in hosts[:cap]:
        desired.add(f"{ip}/32")
    return desired
