#!/bin/bash
# scripts/menu.sh — routepanel management menu (re-run of install.sh when installed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib-install.sh
source "$HERE/scripts/lib-install.sh"
require_root
PY="$PREFIX/.venv/bin/python3"; export ROUTEPANEL_CONFIG="$CONFIG"

show_access() {
    local ip pw
    ip="$(detect_public_ip)"; ip="${ip:-<vps-ip>}"
    pw="$(c_info 'password is hashed; use "change password" to reset')"
    echo "  ssh -L 8080:localhost:8080 root@$ip   → http://localhost:8080"
}

emergency_client() {
    local name; name="$(ask 'Emergency client name' 'recovery')"
    "$PY" "$PREFIX/scripts/mkclient.py" "$name"   # reuse the wizard's client helper
}

while true; do
    cat <<MENU

=== routepanel menu ===
  1) Service status
  2) Show panel access (ssh -L)
  3) Create emergency client
  4) Change panel password
  5) Toggle RU-direct routing
  6) Update routepanel (git pull + migrate + restart)
  7) Uninstall
  0) Quit
MENU
    choice="$(ask 'Choose' '0')"
    case "$choice" in
        1) systemctl --no-pager status routepanel routesyncd routepanel-init | grep -E 'Active|●' || true ;;
        2) show_access ;;
        3) emergency_client ;;
        4) "$PREFIX/.venv/bin/routepanel-passwd"; chmod 600 "$CONFDIR/panel.passwd" ;;
        5) if grep -qE '^ru_direct:[[:space:]]*true' "$CONFIG"; then
               sed -i 's|^ru_direct:.*|ru_direct: false|' "$CONFIG"; systemctl disable --now ru-direct-refresh.timer >/dev/null 2>&1 || true; c_ok "RU-direct OFF"
           else
               sed -i 's|^ru_direct:.*|ru_direct: true|' "$CONFIG"; ipset create -exist ru_direct hash:net; systemctl enable --now ru-direct-refresh.timer >/dev/null 2>&1 || true; "$PY" "$PREFIX/scripts/ru_direct_refresh.py" || true; c_ok "RU-direct ON"
           fi
           systemctl restart routesyncd ;;
        6) if git -C "$PREFIX" rev-parse --git-dir >/dev/null 2>&1; then
               git -C "$PREFIX" pull --ff-only \
                 && "$PREFIX/.venv/bin/pip" install -q -e "$PREFIX" \
                 && systemctl restart routepanel routesyncd \
                 && c_ok "updated"
           else
               c_warn "$PREFIX is not a git checkout, cannot auto-update."
               c_info "Update by re-cloning and re-running the installer, e.g.:"
               c_info "  git clone https://github.com/Wizbos/routepanel /tmp/rp"
               c_info "  sudo rsync -a --exclude='.superpowers' --exclude='.venv' /tmp/rp/ $PREFIX/"
               c_info "  sudo $PREFIX/.venv/bin/pip install -q -e $PREFIX && sudo systemctl restart routepanel routesyncd"
           fi ;;
        7) read -r -p "Type UNINSTALL to confirm: " x </dev/tty
           [[ "$x" == "UNINSTALL" ]] && bash "$PREFIX/scripts/uninstall.sh" || c_warn "cancelled" ;;
        0) exit 0 ;;
        *) c_warn "unknown choice" ;;
    esac
done
