#!/bin/bash
# scripts/uninstall.sh — stop + remove routepanel. Keeps /etc/routepanel (keys, DB)
# unless --purge is given. Never removes the operator's SSH access.
set -euo pipefail
PREFIX="/opt/routepanel"; CONFDIR="/etc/routepanel"
# Capture the awg interface while config.yaml still exists.
AWG_IFACE="$(awk -F'"' '/awg_interface/{print $2}' /etc/routepanel/config.yaml 2>/dev/null)"
systemctl disable --now routepanel routesyncd routepanel-init ru-direct-refresh.timer 2>/dev/null || true
[[ -n "$AWG_IFACE" ]] && systemctl disable --now awg-quick@"$AWG_IFACE" 2>/dev/null || true
rm -f /etc/systemd/system/routepanel*.service /etc/systemd/system/routesyncd.service \
      /etc/systemd/system/ru-direct-refresh.{service,timer}
systemctl daemon-reload
# Our own generated system files (not user data) — safe to remove outright.
rm -f /etc/dnsmasq.d/routepanel-base.conf /etc/sysctl.d/99-routepanel.conf
systemctl restart dnsmasq 2>/dev/null || true
if [[ "${1:-}" == "--purge" ]]; then
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$CONFDIR" "$CONFDIR.removed-$ts"      # archive, never delete keys/DB outright
    echo "config + keys archived to $CONFDIR.removed-$ts"
fi
echo "routepanel removed. Code left at $PREFIX (delete manually if desired)."
