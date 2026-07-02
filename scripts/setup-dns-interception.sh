#!/bin/bash
# scripts/setup-dns-interception.sh
# Reproducible DNS-interception setup (Task 14b, AS DEPLOYED 2026-06-14).
#
# Deviation from the original plan: cloudflared REMOVED `proxy-dns` in v2026.2.0,
# so the DoH proxy is dnscrypt-proxy instead. dnsmasq must run as root (user=root)
# to write ipsets (CAP_NET_ADMIN) -- the unprivileged dnsmasq user fails silently.
#
# Topology:  VPN clients -> AGH (10.8.0.1/172.29.172.1:53)
#                        -> dnsmasq (127.0.0.1:5353, tags rule_<id> ipsets)
#                        -> dnscrypt-proxy (127.0.0.1:5054, DoH cloudflare+quad9)
# AGH fallback_dns = direct DoH, so a dnsmasq/dnscrypt outage degrades routing, not DNS.
set -euo pipefail

echo "== dnscrypt-proxy (DoH) on 127.0.0.1:5054 =="
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dnscrypt-proxy
systemctl disable --now dnscrypt-proxy-resolvconf.service 2>/dev/null || true
mkdir -p /etc/systemd/system/dnscrypt-proxy.socket.d
cat > /etc/systemd/system/dnscrypt-proxy.socket.d/override.conf <<OVR
[Socket]
ListenStream=
ListenDatagram=
ListenStream=127.0.0.1:5054
ListenDatagram=127.0.0.1:5054
OVR
sed -i "s|^listen_addresses = .*|listen_addresses = []|" /etc/dnscrypt-proxy/dnscrypt-proxy.toml
sed -i "s|^server_names = .*|server_names = ['cloudflare', 'quad9-doh-ip4-port443-filter-pri']|" /etc/dnscrypt-proxy/dnscrypt-proxy.toml
systemctl daemon-reload
systemctl enable --now dnscrypt-proxy.socket dnscrypt-proxy.service

echo "== dnsmasq on 127.0.0.1:5353 (ipset tagging; MUST be root) =="
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dnsmasq
cp /opt/routepanel/systemd/dnsmasq-routepanel-base.conf /etc/dnsmasq.d/routepanel-base.conf  # contains user=root
touch /etc/routepanel/dnsmasq-routepanel.conf
systemctl enable dnsmasq
systemctl restart dnsmasq

echo "== AGH upstream repoint (edit + restart) =="
echo "Manual/scripted: set dns.upstream_dns=[127.0.0.1:5353, '[/local.3d-crh.ru/]127.0.0.1:53'],"
echo "dns.upstream_mode=load_balance, dns.fallback_dns=[DoH cloudflare,quad9]; then: systemctl restart adguardhome"

echo "== verify =="
dig @127.0.0.1 -p 5054 example.com +short || true     # dnscrypt
dig @127.0.0.1 -p 5353 cloudflare.com +short || true  # dnsmasq->dnscrypt
echo "done"
