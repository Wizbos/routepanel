# src/routepanel/syncd/ipset_manager.py
import subprocess, os

IPSET_PREFIX = "rule_"   # one hash:net set per domain rule: rule_<id>

def _run(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True, check=True)
    return r.stdout

def ipset_exists(name: str) -> bool:
    """Check a kernel ipset exists by exact name (not the rule_<id> convention --
    used for system sets like ru_ranges/ru_government/telegram_ranges)."""
    return subprocess.run(["ipset", "list", name], capture_output=True).returncode == 0

def ensure_ipset(rule_id, timeout: int = 0) -> None:
    name = f"{IPSET_PREFIX}{rule_id}"
    r = subprocess.run(["ipset", "list", name], capture_output=True)
    if r.returncode != 0:
        args = ["ipset", "create", name, "hash:net"]
        if timeout > 0:
            # Default per-member timeout. dnsmasq (ipset= hooks) and the daemon's
            # resolved IPs add WITHOUT explicit timeout, so they inherit this and
            # expire on their own -- no destructive sweep. (static CIDRs are
            # re-asserted every cycle, so they never age out.)
            args += ["timeout", str(timeout)]
        _run(args)

def get_members(rule_id) -> set[str]:
    name = f"{IPSET_PREFIX}{rule_id}"
    r = subprocess.run(["ipset", "list", name, "-output", "plain"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return set()
    members, in_members = set(), False
    for line in r.stdout.splitlines():
        if line.startswith("Members:"):
            in_members = True
            continue
        if in_members and line.strip():
            members.add(line.strip().split()[0])   # drop trailing "timeout N"
    return members

def add_ip(rule_id, member: str) -> None:
    _run(["ipset", "add", "-exist", f"{IPSET_PREFIX}{rule_id}", member])

def remove_ip(rule_id, member: str) -> None:
    subprocess.run(["ipset", "del", f"{IPSET_PREFIX}{rule_id}", member], capture_output=True)

def sync_ips(rule_id, desired: set[str]) -> tuple[set[str], set[str]]:
    ensure_ipset(rule_id)
    current = get_members(rule_id)
    to_add = desired - current
    to_remove = current - desired
    for m in to_add:
        add_ip(rule_id, m)
    for m in to_remove:
        remove_ip(rule_id, m)
    return to_add, to_remove

def save_all(path: str) -> None:
    out = _run(["ipset", "save"])
    with open(path, "w") as f:
        f.write(out)

def restore_all(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        data = f.read()
    subprocess.run(["ipset", "restore"], input=data, text=True, capture_output=True)

def refresh_members_batch(rule_id, members: set[str], timeout: int = 0) -> set[str]:
    """ADD-ONLY refresh of a rule's ipset in ONE `ipset restore -exist` txn.
    `members` = resolved IPs PLUS the rule's static CIDRs (hash:net holds both).
    Never removes -- so it won't clobber the live IPs dnsmasq adds at lookup time;
    stale resolved IPs fall out via the set timeout. Returns members new this call."""
    ensure_ipset(rule_id, timeout)
    if not members:
        return set()
    new = members - get_members(rule_id)
    lines = [f"add {IPSET_PREFIX}{rule_id} {m} -exist" for m in members]
    subprocess.run(["ipset", "restore", "-exist"],
                   input="\n".join(lines) + "\n", text=True, capture_output=True)
    return new

def destroy_ipset(rule_id) -> None:
    """Reap a deleted rule's set. The chain stops matching it on the next rebuild;
    this frees the kernel set. Safe if it doesn't exist."""
    subprocess.run(["ipset", "destroy", f"{IPSET_PREFIX}{rule_id}"], capture_output=True)
