#!/bin/bash
# install.sh — routepanel interactive installer.
#   sudo bash install.sh          first run = wizard; later runs = menu (see scripts/menu).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib-install.sh
source "$HERE/scripts/lib-install.sh"

require_root
if [[ -f "$CONFDIR/.installed" ]]; then
    exec bash "$HERE/scripts/menu.sh"     # completed install -> menu mode
fi

echo "=== routepanel installer ==="
check_os
SSH_PORT="$(detect_ssh_port)"; SSH_PORT="${SSH_PORT:-22}"
protect_ssh "$SSH_PORT"

# All prompts accept a matching RP_* env var for unattended installs:
#   RP_PUBIP RP_AWG_PORT RP_SUBNET RP_CLIENT RP_PASSWORD RP_RU_DIRECT
# With no env var AND no tty, each falls back to its default (RP_PASSWORD -> auto).
WAN="$(detect_wan_iface)"; [[ -n "$WAN" ]] || die "could not detect the WAN interface"
PUBIP="${RP_PUBIP:-$(detect_public_ip)}"
[[ -n "$PUBIP" ]] || PUBIP="$(ask 'Public IPv4 of this VPS' '')"
[[ -n "$PUBIP" ]] || die "need a public IPv4 for client configs"

AWG_PORT="$(ask_var RP_AWG_PORT 'AmneziaWG UDP port' "$(rand_port)")"
SUBNET="$(ask_var RP_SUBNET 'Client tunnel subnet' '10.8.0.0/24')"
CLIENT1="$(ask_var RP_CLIENT 'First client (device) name' 'phone')"
if [[ -n "${RP_PASSWORD:-}" ]]; then
    PW="$RP_PASSWORD"
elif has_tty; then
    read -r -s -p "Panel password (blank = auto-generate): " PW </dev/tty; echo
else
    PW=""
fi
[[ -n "$PW" ]] || { PW="$(head -c12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c16)"; c_info "generated panel password: $PW"; }
RU_DIRECT="$(ask_var RP_RU_DIRECT 'Route known RU networks direct? (yes/no)' 'yes')"

c_info "Installing packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip iptables ipset dnsmasq dnscrypt-proxy \
    curl ca-certificates wireguard-tools rsync >/dev/null

# AmneziaWG: kernel module from the amnezia PPA, built via DKMS.
if install_amneziawg; then
    c_ok "AmneziaWG kernel module ready"
else
    die "could not install AmneziaWG — ensure linux-headers-$(uname -r) is available (or install amneziawg manually), then re-run"
fi

c_info "Installing routepanel to $PREFIX…"
mkdir -p "$PREFIX" "$CONFDIR" "$CONFDIR/exits"
rsync -a --exclude='.superpowers' --exclude='.venv' \
      --exclude='__pycache__' --exclude='*.pyc' "$HERE/" "$PREFIX/"
python3 -m venv "$PREFIX/.venv"
"$PREFIX/.venv/bin/pip" install -q -e "$PREFIX"

# config.yaml from the example, patched with answers.
backup_file "$CONFIG"
cp "$PREFIX/config.yaml.example" "$CONFIG"
sed -i "s|^wan_interface:.*|wan_interface: \"$WAN\"|" "$CONFIG"
[[ "$RU_DIRECT" =~ ^[Yy] ]] && sed -i "s|^ru_direct:.*|ru_direct: true|" "$CONFIG"
touch "$CONFDIR/db.sqlite"; chmod 600 "$CONFDIR/db.sqlite"

# Server identity + password + DNS chain.
ROUTEPANEL_CONFIG="$CONFIG" "$PREFIX/.venv/bin/routepanel-awg-init" \
    --endpoint "$PUBIP:$AWG_PORT" --subnet "$SUBNET" --port "$AWG_PORT"
ROUTEPANEL_CONFIG="$CONFIG" "$PREFIX/.venv/bin/routepanel-passwd" "$PW"
chmod 600 "$CONFDIR/panel.passwd"
bash "$PREFIX/scripts/setup-dns.sh"

# systemd units.
for u in routepanel-init routepanel routesyncd ru-direct-refresh; do
    [[ -f "$PREFIX/systemd/$u.service" ]] && install -m0644 "$PREFIX/systemd/$u.service" /etc/systemd/system/
done
install -m0644 "$PREFIX/systemd/ru-direct-refresh.timer" /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now awg-quick@"$(awk -F'"' '/awg_interface/{print $2}' "$CONFIG")" >/dev/null 2>&1 || true
systemctl enable --now routepanel-init routepanel routesyncd >/dev/null
[[ "$RU_DIRECT" =~ ^[Yy] ]] && { systemctl enable --now ru-direct-refresh.timer >/dev/null; "$PREFIX/.venv/bin/python3" "$PREFIX/scripts/ru_direct_refresh.py" || true; }

# First client + QR in the terminal.
CID="$(ROUTEPANEL_CONFIG="$CONFIG" "$PREFIX/.venv/bin/python3" - "$CLIENT1" <<'PY'
import sys, asyncio
from routepanel.db import open_db
from routepanel.config import get_config
from routepanel import awgserver
async def go(name):
    db = await open_db()
    srv = await awgserver.get_server(db)
    async with db.execute("SELECT address FROM clients") as c:
        taken = {r["address"] for r in await c.fetchall()}
    ip = awgserver.allocate_client_ip(taken, srv["subnet"])
    priv, pub = awgserver.gen_keypair(); psk = awgserver.gen_psk()
    cur = await db.execute("INSERT INTO clients(name,public_key,private_key,psk,address) VALUES(?,?,?,?,?)",
                           (name, pub, priv, psk, ip)); await db.commit()
    await awgserver.apply_server_conf(db, get_config()); await db.close()
    print(cur.lastrowid)
asyncio.run(go(sys.argv[1]))
PY
)"

echo
echo "=== routepanel is up ==="
ROUTEPANEL_CONFIG="$CONFIG" "$PREFIX/.venv/bin/python3" - "$CID" <<'PY'
import sys, asyncio, io
from routepanel.db import open_db
from routepanel import awgserver
try:
    import qrcode
except Exception:
    qrcode = None
async def go(cid):
    db = await open_db(); srv = await awgserver.get_server(db)
    async with db.execute("SELECT * FROM clients WHERE id=?", (int(cid),)) as c:
        cl = dict(await c.fetchone())
    await db.close()
    conf = awgserver.render_client_conf(srv, cl)
    if qrcode:
        q = qrcode.QRCode(border=1); q.add_data(conf); q.make()
        q.print_ascii(invert=True)
    print("\n--- client config (also available in the panel) ---\n" + conf)
asyncio.run(go(sys.argv[1]))
PY

# Default-policy announcement (spec requirement).
if [[ "$RU_DIRECT" =~ ^[Yy] ]]; then
  echo "POLICY: all client traffic → your first exit node; known RU networks → direct."
else
  echo "POLICY: all client traffic → your first exit node. (RU-direct disabled.)"
fi
echo "You have no exit nodes yet, so ALL traffic currently goes DIRECT from this VPS's IP."
echo "Add an exit node (paste a WireGuard/AmneziaWG config via the exit API) to start tunneling."
echo
echo "Open the panel over an SSH tunnel:"
echo "  ssh -L 8080:localhost:8080 root@$PUBIP   then browse http://localhost:8080"
echo "  panel password: $PW"
echo "Re-run 'sudo bash install.sh' any time for the management menu."

touch "$CONFDIR/.installed"
