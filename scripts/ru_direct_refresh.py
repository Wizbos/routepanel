#!/usr/bin/env python3
"""Populate the ru_direct ipset from an aggregated RU IPv4 zone (default: ipdeny).
routing_manager.system_ipsets maps ru_direct -> 'clear' (direct egress) when
cfg.ru_direct is on, so Russian networks (banks, gov portals, local services) skip
the exit tunnel. Run by a weekly systemd timer; safe by hand. Keeps the existing
set on any fetch/parse failure so a bad refresh never blackholes RU traffic."""
import ipaddress, subprocess, sys, urllib.request

IPSET = "ru_direct"
DEFAULT_URL = "https://www.ipdeny.com/ipblocks/data/aggregated/ru-aggregated.zone"

def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode()

def parse_zone(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if ipaddress.ip_network(line).version == 4:
                out.append(line)
        except ValueError:
            continue
    return out

def apply_ipset(cidrs, ipset: str = IPSET, runner=subprocess.run) -> None:
    """Build a temp set and atomically `ipset swap` it in, so the chain's match-set
    never observes a half-populated or empty ru_direct."""
    tmp = f"{ipset}_tmp"
    runner(["ipset", "create", "-exist", tmp, "hash:net"], check=True)
    runner(["ipset", "flush", tmp], check=True)
    payload = "".join(f"add {tmp} {c}\n" for c in cidrs)
    runner(["ipset", "restore", "-exist"], input=payload, text=True, check=True)
    runner(["ipset", "create", "-exist", ipset, "hash:net"], check=True)
    runner(["ipset", "swap", tmp, ipset], check=True)
    runner(["ipset", "destroy", tmp], check=True)

def main(url: str | None = None) -> None:
    if url is None:
        try:
            from routepanel.config import get_config
            url = get_config().ru_direct_url or DEFAULT_URL
        except Exception:
            url = DEFAULT_URL
    try:
        cidrs = parse_zone(_default_fetch(url))
    except Exception as e:
        print(f"ru_direct refresh failed, keeping existing set: {e}", file=sys.stderr)
        return
    if not cidrs:
        print("ru_direct: source returned 0 prefixes, keeping existing set", file=sys.stderr)
        return
    apply_ipset(cidrs)
    print(f"ru_direct: {len(cidrs)} prefixes")

if __name__ == "__main__":
    main(*sys.argv[1:])
