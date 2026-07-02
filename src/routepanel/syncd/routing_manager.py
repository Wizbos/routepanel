# src/routepanel/syncd/routing_manager.py
import subprocess
import logging
from routepanel.config import get_config
from routepanel.syncd import ipset_manager

log = logging.getLogger("routesyncd")

# Tables that carry the HOST's own traffic. A routepanel exit must never install
# a default route (or fwmark rule) here -- doing so hijacks the VPS's egress and
# isolates the box. Enforced below AND validated at the API layer (panel/routes/exits.py).
_PROTECTED_TABLES = {"main", "local", "default"}

CHAIN = "ROUTEPANEL"   # owned mangle chain -- flushed + rebuilt in precedence order

SYSTEM_IPSETS = [
    ("ru_ranges",       "clear"),   # -> direct
    ("ru_government",   "clear"),   # -> direct
    ("telegram_ranges", 100),       # -> forced VPN
]

# Private/corp destinations must NEVER be marked toward the VPN -- the catch-all
# default would otherwise send corp-internal traffic out doprax. Cleared right
# after the default mark.
LOCAL_DIRECT = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"]

def _ifaces() -> list[str]:
    return get_config().client_interfaces

def _run(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)

def _ipt(*args: str) -> None:
    """iptables -t mangle, idempotent append (skip if the rule already exists)."""
    if _run(["iptables", "-t", "mangle", "-C", *args]).returncode != 0:
        _run(["iptables", "-t", "mangle", "-A", *args], check=True)

def ensure_chain_and_jumps() -> None:
    """Create the owned chain and the per-interface jumps into it (idempotent)."""
    _run(["iptables", "-t", "mangle", "-N", CHAIN])  # returns !=0 if exists -- ignored
    for iface in _ifaces():
        _ipt("PREROUTING", "-i", iface, "-j", CHAIN)

def _mark(fwmark: int) -> list[str]:
    return ["-j", "MARK", "--and-mark", "0x0"] if fwmark == 0 \
        else ["-j", "MARK", "--set-mark", str(fwmark)]

def rebuild_chain(rules: list[dict], effective_fwmark: dict, default_fwmark: int) -> None:
    """Flush the owned chain and re-append in precedence order:
       1)  default catch-all -> default exit's EFFECTIVE fwmark
       1b) RFC1918/local     -> direct
       2)  system ipsets (ru/gov clear, telegram force-VPN)
       3)  one match per rule: rule_<id> -> that rule's EFFECTIVE exit fwmark
    `effective_fwmark` maps rule id -> fwmark for this cycle (failover-resolved).
    Rebuilding guarantees ordering and drops matches for deleted rules. The brief
    flush window only risks default-routing a packet for a sub-ms gap."""
    ensure_chain_and_jumps()
    _run(["iptables", "-t", "mangle", "-F", CHAIN], check=True)

    def app(*rule: str) -> None:
        _run(["iptables", "-t", "mangle", "-A", CHAIN, *rule], check=True)

    # 1. default catch-all -> default exit's effective fwmark
    app(*_mark(default_fwmark))
    # 1b. private/corp destinations stay direct (never sent to the VPN)
    for cidr in LOCAL_DIRECT:
        app("-d", cidr, "-j", "MARK", "--and-mark", "0x0")
    # 2. system overrides -- gated on the ipset actually existing. These sets are
    # normally created by routepanel-init.sh at boot, but routesyncd can race that
    # script (or a set can be dropped later); `--match-set <missing>` makes
    # iptables -A fail, which must not abort the rest of the chain rebuild.
    for name, action in SYSTEM_IPSETS:
        if not ipset_manager.ipset_exists(name):
            log.error("system ipset '%s' missing; skipping its chain rule this cycle", name)
            continue
        if action == "clear":
            app("-m", "set", "--match-set", name, "dst", "-j", "MARK", "--and-mark", "0x0")
        else:
            app("-m", "set", "--match-set", name, "dst", "-j", "MARK", "--set-mark", str(action))
    # 3. one match per rule -> its effective exit fwmark (evaluated last, win)
    for r in rules:
        fwmark = effective_fwmark.get(r["id"], 0)
        app("-m", "set", "--match-set", f"rule_{r['id']}", "dst", *_mark(fwmark))

def apply_ip_rules(exits: list[dict]) -> None:
    """Ensure `ip rule fwmark N lookup <table>` for each non-direct exit."""
    for e in exits:
        if e["fwmark"] == 0:
            continue
        if e["routing_table"] in _PROTECTED_TABLES:
            log.error("exit %s: refusing fwmark rule into protected table '%s'",
                      e["id"], e["routing_table"])
            continue
        r = _run(["ip", "rule", "show", "fwmark", str(e["fwmark"])])
        if e["routing_table"] not in r.stdout:
            _run(["ip", "rule", "add", "fwmark", str(e["fwmark"]),
                  "lookup", e["routing_table"], "priority", str(100 + e["fwmark"])], check=True)

def apply_routing_tables(exits: list[dict]) -> None:
    """Ensure a default route in each VPN routing table.

    Not check=True: at boot an exit's rpx interface may not be up yet (awg-quick
    hasn't run this cycle), and `ip route replace ... dev <iface>` fails when the
    device doesn't exist. That must be logged and skipped, not raised -- an
    exception here would abort the whole reconcile, including exits whose
    interface IS present. exit_iface_manager brings the interface up; the next
    sync cycle retries this route once it exists."""
    for e in exits:
        if e["fwmark"] == 0:
            continue
        if e["routing_table"] in _PROTECTED_TABLES:
            log.error("exit %s: refusing default route into protected table '%s' "
                      "(would hijack host egress)", e["id"], e["routing_table"])
            continue
        r = _run(["ip", "route", "replace", "default", "dev", e["interface"],
                  "table", e["routing_table"]])
        if r.returncode != 0:
            log.error("exit %s: failed to set default route via %s (device may not "
                      "be up yet): %s", e["id"], e["interface"], r.stderr.strip())


def _nat(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["iptables", "-t", "nat", *args], capture_output=True, text=True, check=check)

def ensure_wan_nat(rules: list[dict], wan_interface: str) -> None:
    """MASQUERADE each rule's dst out the WAN interface. Needed when an
    OSPF-distributed rule exits 'direct' (eth0): corp clients' private source IPs
    must be NATed or return traffic is lost. Harmless for VPN-exit rules (their
    traffic leaves via the tunnel, which has its own MASQUERADE), since this only
    matches packets that actually egress the WAN."""
    for r in rules:
        name = f"rule_{r['id']}"
        if _nat(["-C", "POSTROUTING", "-o", wan_interface, "-m", "set",
                 "--match-set", name, "dst", "-j", "MASQUERADE"]).returncode != 0:
            _nat(["-A", "POSTROUTING", "-o", wan_interface, "-m", "set",
                  "--match-set", name, "dst", "-j", "MASQUERADE"], check=True)

def remove_wan_nat(rule_id, wan_interface: str) -> None:
    """Drop a deleted rule's WAN MASQUERADE BEFORE its ipset is destroyed
    (a live iptables match-set ref blocks `ipset destroy`)."""
    _nat(["-D", "POSTROUTING", "-o", wan_interface, "-m", "set",
          "--match-set", f"rule_{rule_id}", "dst", "-j", "MASQUERADE"])

def reconcile(exits: list[dict], rules: list[dict], effective_fwmark: dict,
              default_fwmark: int) -> None:
    """Full idempotent apply. Safe to call at boot AND on every sync, so exits/rules
    added through the panel take effect without a reboot, and failover = one rebuild."""
    apply_routing_tables(exits)
    apply_ip_rules(exits)
    rebuild_chain(rules, effective_fwmark, default_fwmark)
    ensure_wan_nat(rules, get_config().wan_interface)
