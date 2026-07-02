# src/routepanel/cidr.py
"""Shared CIDR/IP normalization.

A bare host IP is normalized to a /32 (IPv4) or /128 (IPv6) prefix. Used by the
panel API to reject bad input with HTTP 422 and store canonical prefixes, and by
the FRR sync to defensively skip anything malformed -- so a single bad entry can
never make `vtysh ip route <prefix>` fail and abort the whole OSPF push.
"""
import ipaddress


def normalize_cidr(value: str) -> str:
    """Return the canonical ``network/prefixlen`` form of a CIDR or bare IP.

    A bare host IP becomes ``/32`` (v4) or ``/128`` (v6). ``strict=False`` means
    host bits are masked off rather than rejected (``10.0.0.5/24`` -> ``10.0.0.0/24``).
    Raises ``ValueError`` if the value is not a parseable IP/CIDR.
    """
    return str(ipaddress.ip_network(str(value).strip(), strict=False))


def normalize_cidrs(values) -> list[str]:
    """Normalize a list of CIDRs/IPs, preserving order and de-duplicating.

    Raises ``ValueError`` naming the offending entry on the first bad value.
    """
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        try:
            n = normalize_cidr(v)
        except ValueError as e:
            raise ValueError(f"invalid CIDR/IP {v!r}: {e}")
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out
