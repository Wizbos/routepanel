# src/routepanel/syncd/frr_manager.py
import subprocess
import logging
from routepanel.cidr import normalize_cidr

log = logging.getLogger("routesyncd")

def _vtysh(*commands: str) -> str:
    args = ["vtysh"]
    for cmd in commands:
        args += ["-c", cmd]
    r = subprocess.run(args, capture_output=True, text=True, check=True)
    return r.stdout

def add_route(prefix: str, next_hop: str = "Null0") -> None:
    # prefix carries its own mask (a resolved IP arrives as x.x.x.x/32; a static
    # CIDR as x.x.x.x/24) so we advertise it verbatim.
    _vtysh("configure terminal", f"ip route {prefix} {next_hop}")

def remove_route(prefix: str, next_hop: str = "Null0") -> None:
    _vtysh("configure terminal", f"no ip route {prefix} {next_hop}")

def get_static_routes() -> set[str]:
    out = _vtysh("show ip route static")
    routes = set()
    for line in out.splitlines():
        if not line.startswith("S"):
            continue
        for part in line.split():
            if "/" in part and part.split("/")[0].count(".") == 3:
                routes.add(part)      # full prefix incl. mask: 1.2.3.4/32, 1.2.3.0/24
                break
    return routes

def _sanitize(prefixes) -> set[str]:
    """Normalize prefixes to canonical ``net/mask`` (a bare IP -> /32) and drop
    anything unparseable. This is the guard against the 2026-06-15 outage: a
    maskless IP in a rule's static_cidrs would make ``vtysh ip route`` exit
    non-zero and abort the entire OSPF push (and, downstream, roll back the
    sync's DB commit). Normalizing fixes the common case; skipping covers the
    rest -- one bad entry can never poison the batch."""
    good: set[str] = set()
    for p in prefixes:
        try:
            good.add(normalize_cidr(p))
        except ValueError:
            log.warning("FRR: skipping invalid prefix %r (not a valid CIDR/IP)", p)
    return good

def sync_routes(desired: set[str], next_hop: str = "Null0") -> tuple[set[str], set[str]]:
    desired = _sanitize(desired)
    current = get_static_routes()
    to_add = desired - current
    to_remove = current - desired
    for p in to_add:
        add_route(p, next_hop)
    for p in to_remove:
        remove_route(p, next_hop)
    return to_add, to_remove

def sync_routes_batch(desired: set[str], next_hop: str = "Null0") -> tuple[set[str], set[str]]:
    """Same diff as sync_routes, but emit all add/withdraw lines in ONE vtysh
    `configure terminal` transaction. `desired` holds full prefixes (resolved IPs
    as /32, static CIDRs verbatim). Avoids an LSA storm (one commit per sync)."""
    desired = _sanitize(desired)
    current = get_static_routes()
    to_add = desired - current
    to_remove = current - desired
    if not to_add and not to_remove:
        return set(), set()
    cmds = ["configure terminal"]
    cmds += [f"ip route {p} {next_hop}" for p in to_add]
    cmds += [f"no ip route {p} {next_hop}" for p in to_remove]
    _vtysh(*cmds)
    return to_add, to_remove
