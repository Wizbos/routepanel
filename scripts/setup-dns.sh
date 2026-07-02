#!/bin/bash
# scripts/setup-dns.sh — install the dnsmasq(ipset-tagging) + dnscrypt-proxy chain.
# dnsmasq listens on 127.0.0.1:5353, tags routed domains into ipsets, forwards
# upstream to dnscrypt-proxy (DoH) on 127.0.0.1:5054.
set -euo pipefail

# DNAT of client :53 rewrites the destination to 127.0.0.1; the kernel drops
# packets routed to loopback from a non-loopback interface unless route_localnet
# is enabled. Persist it and apply now.
install -m 0644 /dev/stdin /etc/sysctl.d/99-routepanel.conf <<'SYSCTL'
# routepanel: allow DNAT of client DNS to the local resolver on 127.0.0.1
net.ipv4.conf.all.route_localnet = 1
# routepanel: this box is a gateway — forward client traffic
net.ipv4.ip_forward = 1
SYSCTL
sysctl -w net.ipv4.conf.all.route_localnet=1 >/dev/null
sysctl -w net.ipv4.ip_forward=1 >/dev/null

# route_localnet=1 on `all` also lets off-box packets addressed to 127.0.0.0/8
# reach loopback services; drop those on the WAN interface only (the DNAT'd
# client DNS arrives on the client/awg interface, so it is not affected).
WAN="$(awk -F'"' '/wan_interface/{print $2}' /etc/routepanel/config.yaml 2>/dev/null)"
if [[ -n "$WAN" ]]; then
    iptables -C INPUT -i "$WAN" -d 127.0.0.0/8 -j DROP 2>/dev/null \
        || iptables -I INPUT 1 -i "$WAN" -d 127.0.0.0/8 -j DROP
fi

install -m 0644 /opt/routepanel/systemd/dnsmasq-routepanel-base.conf \
    /etc/dnsmasq.d/routepanel-base.conf
touch /etc/routepanel/dnsmasq-routepanel.conf

# dnscrypt-proxy: minimal DoH resolver on 127.0.0.1:5054.
DNSCRYPT_TOML=/etc/dnscrypt-proxy/dnscrypt-proxy.toml
if [[ -f "$DNSCRYPT_TOML" ]]; then
    cp -a "$DNSCRYPT_TOML" "$DNSCRYPT_TOML.bak.$(date -u +%Y%m%dT%H%M%SZ)"
fi
cat > "$DNSCRYPT_TOML" <<'TOML'
listen_addresses = ['127.0.0.1:5054']
server_names = ['cloudflare', 'google']
require_dnssec = false
block_ipv6 = true
[sources.public-resolvers]
urls = ['https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/public-resolvers.md']
cache_file = '/var/cache/dnscrypt-proxy/public-resolvers.md'
minisign_key = 'RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3'
TOML

# Ubuntu ships a dnscrypt-proxy.socket unit that pre-binds 127.0.2.1:53 and, via
# socket activation, overrides our listen_addresses (dnscrypt logs "Wiring systemd
# socket … 127.0.2.1:53" and ignores the toml). Disable the socket so the service
# starts standalone and honours listen_addresses = 127.0.0.1:5054.
systemctl disable --now dnscrypt-proxy.socket >/dev/null 2>&1 || true
systemctl enable dnscrypt-proxy >/dev/null 2>&1 || true
systemctl restart dnscrypt-proxy || true
systemctl restart dnsmasq

# Wait for dnscrypt to bind :5054 (it fetches its resolver list on first start).
for _ in $(seq 1 15); do
    ss -tulnp 2>/dev/null | grep -q '127.0.0.1:5054' && break
    sleep 1
done
echo "[setup-dns] dnsmasq(:5353) + dnscrypt-proxy(:5054) configured"
