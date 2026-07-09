# src/routepanel/domainval.py
"""Shared domain-name validation.

`dnsmasq_manager.render_fragment` joins each rule's domains into a single
line: ``ipset=/dom1/dom2/.../rule_<id>``. That format is '/'-delimited and
dnsmasq treats '#' as a start-of-comment marker, so a domain containing '/',
whitespace, '#', control characters, or an empty domain corrupts the line --
best case a `dnsmasq --test` syntax failure that keeps the fragment from ever
being applied (see dnsmasq_manager.check_config / the 2026-07-09 incident,
where an unvalidated fragment reached a downstream Pi-hole and took DNS down
for 20 minutes), worst case a domain holding a literal newline injects an
extra config directive into the fragment.

Used by the panel API to reject bad input with HTTP 422 (`validate_domains`),
and by the fragment generator to defensively drop anything malformed so one
bad row -- e.g. written before this validation existed, or inserted directly
into the DB outside the API -- can never break the whole fragment
(`filter_valid_domains`). Mirrors cidr.py's `normalize_cidrs` / frr_manager's
`_sanitize`.
"""
import re

# RFC 1035-ish hostname label: alnum + hyphens, hyphen never leading/trailing,
# 1-63 chars. Requires at least one '.' (a bare label like "localhost" is not
# a routable internet domain and isn't a shape the service library or any
# existing rule uses).
_LABEL = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
_DOMAIN_RE = re.compile(rf"^{_LABEL}(\.{_LABEL})+$")
MAX_DOMAIN_LEN = 253  # RFC 1035 total length limit


def is_valid_domain(value) -> bool:
    """True iff `value` is a plain-ASCII hostname safe to embed in a dnsmasq
    ``ipset=/.../`` fragment line.

    Rejects: non-str, leading/trailing whitespace, empty string, anything
    over the DNS length limit, non-ASCII (IDN domains must be punycode-
    encoded by the caller), and anything not matching a plain dotted-label
    hostname -- which also excludes '/', '#', internal whitespace, and
    control characters, since none of those are valid label characters.
    """
    if not isinstance(value, str):
        return False
    if value != value.strip():
        return False
    if not value or len(value) > MAX_DOMAIN_LEN:
        return False
    if not value.isascii():
        return False
    return bool(_DOMAIN_RE.match(value))


def validate_domains(values) -> list[str]:
    """Validate a list of rule domains, preserving order.

    Raises ``ValueError`` naming the offending entry on the first bad value --
    same contract as ``cidr.normalize_cidrs``, so panel routes can catch it
    and return HTTP 422.
    """
    for v in values:
        if not is_valid_domain(v):
            raise ValueError(f"invalid domain {v!r}")
    return list(values)


def filter_valid_domains(values, on_invalid=None) -> list[str]:
    """Best-effort filter used by the fragment generator: drop anything that
    wouldn't pass `is_valid_domain`, calling `on_invalid(value)` for each
    dropped entry (e.g. to log it) instead of raising. Defense in depth for
    rows that predate this validation or were written outside the panel API.
    """
    out: list[str] = []
    for v in values:
        if is_valid_domain(v):
            out.append(v)
        elif on_invalid:
            on_invalid(v)
    return out
