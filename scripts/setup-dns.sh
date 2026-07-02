#!/bin/bash
# scripts/setup-dns.sh — install the dnsmasq(ipset-tagging) + dnscrypt-proxy chain.
# dnsmasq listens on 127.0.0.1:5353, tags routed domains into ipsets, forwards
# upstream to dnscrypt-proxy (DoH) on 127.0.0.1:5054.
set -euo pipefail

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
[sources.public-resolvers]
urls = ['https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/public-resolvers.md']
cache_file = '/var/cache/dnscrypt-proxy/public-resolvers.md'
minisign_key = 'RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3'
TOML

systemctl enable --now dnscrypt-proxy >/dev/null 2>&1 || systemctl restart dnscrypt-proxy || true
systemctl restart dnsmasq
echo "[setup-dns] dnsmasq(:5353) + dnscrypt-proxy(:5054) configured"
