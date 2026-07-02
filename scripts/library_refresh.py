#!/usr/bin/env python3
"""Refresh auto-updatable CIDR sets in the service_library DB table.
Driven by each pack's `refresh` entry in service_library.json. IPv4 only
(routepanel is IPv4-only; AAAA is suppressed for routed domains). Run by a
systemd timer (Plan 2); safe to run by hand. Never removes a pack's cidrs on
fetch failure -- a failing source keeps yesterday's set."""
import ipaddress, json, pathlib, sqlite3, sys, urllib.request

LIB_PATH = pathlib.Path(__file__).resolve().parents[1] / "service_library.json"

def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode()

def _v4(cidrs) -> list[str]:
    out = []
    for c in cidrs:
        try:
            if ipaddress.ip_network(c.strip()).version == 4:
                out.append(c.strip())
        except ValueError:
            continue
    return out

def fetch_cidrs(pack: dict, fetch=_default_fetch) -> list[str]:
    ref = pack["refresh"]
    raw = fetch(ref["url"])
    if ref["format"] == "goog-json":
        return _v4(p.get("ipv4Prefix", "") for p in json.loads(raw)["prefixes"])
    if ref["format"] == "cidr-lines":
        return _v4(l for l in raw.splitlines() if l.strip() and not l.startswith("#"))
    if ref["format"] == "ripestat-as":
        return _v4(p["prefix"] for p in json.loads(raw)["data"]["prefixes"])
    raise ValueError(f"unknown refresh format {ref['format']!r}")

def main(db_path: str = "/etc/routepanel/db.sqlite") -> None:
    packs = [p for p in json.loads(LIB_PATH.read_text()) if "refresh" in p]
    db = sqlite3.connect(db_path)
    for p in packs:
        try:
            cidrs = fetch_cidrs(p)
        except Exception as e:
            print(f"{p['id']}: refresh failed, keeping previous set: {e}", file=sys.stderr)
            continue
        if not cidrs:
            print(f"{p['id']}: source returned 0 prefixes, keeping previous set", file=sys.stderr)
            continue
        db.execute("UPDATE service_library SET cidrs=?, updated_at=datetime('now') WHERE id=?",
                   (json.dumps(sorted(cidrs)), p["id"]))
        print(f"{p['id']}: {len(cidrs)} prefixes")
    db.commit(); db.close()

if __name__ == "__main__":
    main(*sys.argv[1:])
