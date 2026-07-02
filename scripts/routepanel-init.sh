#!/bin/bash
# scripts/routepanel-init.sh
# Run at boot: restore ipsets, set up ip rules + routing tables from DB.
set -euo pipefail

DB="/etc/routepanel/db.sqlite"
IPSETS_SAVE="/etc/routepanel/ipsets.save"

log() { echo "[routepanel-init] $*" | systemd-cat -t routepanel-init; echo "[routepanel-init] $*"; }

# 1. Restore persisted ipsets
if [[ -f "$IPSETS_SAVE" ]]; then
    log "Restoring ipsets from $IPSETS_SAVE"
    ipset restore -exist < "$IPSETS_SAVE" || true
fi

# 2. Ensure any system ipsets a deployment has configured exist before the
#    ROUTEPANEL chain (which references them via --match-set) is built. Empty
#    in the OSS default (routing_manager.SYSTEM_IPSETS is []) -- add names here
#    if your deployment populates SYSTEM_IPSETS with custom overrides.
SYSTEM_IPSET_NAMES=()
for name in "${SYSTEM_IPSET_NAMES[@]}"; do
    ipset create -exist "$name" hash:net
done

# 3. Ensure per-rule ipsets + apply routing (ip rules, tables, owned chain).
#    Use the venv interpreter so `import routepanel...` resolves, and rely on
#    routing_manager.reconcile so init and the daemon share one code path.
PY="/opt/routepanel/.venv/bin/python3"
"$PY" - << 'PYEOF'
import asyncio, sqlite3, json
from routepanel.config import get_config
from routepanel.db import open_db as _open_db
from routepanel.settings import get_default_exit_id as _gdei
from routepanel.syncd import ipset_manager, routing_manager
cfg = get_config()
db = sqlite3.connect("/etc/routepanel/db.sqlite")
db.row_factory = sqlite3.Row
exits = [dict(r) for r in db.execute("SELECT * FROM exits").fetchall()]
rules = [dict(r) for r in db.execute("SELECT * FROM domain_rules").fetchall()]
db.close()
fwmark_of = {e["id"]: e["fwmark"] for e in exits}
# Boot-time: health is unknown, so use each rule's CONFIGURED exit (routesyncd
# refines via failover within one cycle). Seed static CIDRs so routing works
# immediately, before the first resolver pass.
for r in rules:
    ipset_manager.ensure_ipset(r["id"], cfg.ipset_timeout_sec)   # match-set targets must exist first
    cidrs = set(json.loads(r.get("static_cidrs") or "[]"))
    if cidrs:
        ipset_manager.refresh_members_batch(r["id"], cidrs, cfg.ipset_timeout_sec)
effective_fwmark = {r["id"]: fwmark_of.get(r["exit_id"], 0) for r in rules}

async def _resolve_default():
    # DB setting (panel-controlled) wins over the static config default -- same
    # precedence routesyncd uses, so boot-time routing matches steady state.
    _db = await _open_db()
    try:
        return await _gdei(_db, cfg)
    finally:
        await _db.close()

default_exit_id = asyncio.run(_resolve_default())
default_fwmark = fwmark_of.get(default_exit_id, 0)

import sqlite3 as _sq
_c = _sq.connect("/etc/routepanel/db.sqlite"); _c.row_factory = _sq.Row
_row = _c.execute("SELECT value FROM settings WHERE key='awg.subnet'").fetchone()
_c.close()
client_subnet = _row["value"] if _row else None
routing_manager.reconcile(exits, rules, effective_fwmark, default_fwmark, client_subnet)
print(f"[routepanel-init] reconciled: {len(exits)} exits, {len(rules)} rules")
PYEOF

# 4. Ensure the dnsmasq fragment exists (empty is fine) so dnsmasq's include
#    never fails before routesyncd has written it. routesyncd regenerates it.
touch /etc/routepanel/dnsmasq-routepanel.conf

# 5. Allow the panel port (8080) from private RFC1918 networks only (panel is
#    LAN/VPN-restricted; no auth token). Idempotent. Persisted via netfilter-persistent.
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
    iptables -C INPUT -p tcp -s "$net" --dport 8080 -j ACCEPT 2>/dev/null || \
    iptables -I INPUT 1 -p tcp -s "$net" --dport 8080 -j ACCEPT
done

# 6. DNS forwarding port: an upstream resolver (e.g. a site-local DNS server)
#    may forward routed domains here to this host's dnsmasq. Private RFC1918
#    only; WAN is blocked by the INPUT DROP policy. Idempotent. Persisted via
#    netfilter-persistent.
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
    for proto in udp tcp; do
        iptables -C INPUT -p "$proto" -s "$net" --dport 5353 -j ACCEPT 2>/dev/null || \
        iptables -I INPUT 1 -p "$proto" -s "$net" --dport 5353 -j ACCEPT
    done
done

log "Init complete"
