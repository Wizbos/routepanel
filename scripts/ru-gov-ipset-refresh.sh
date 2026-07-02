#!/bin/bash
# scripts/ru-gov-ipset-refresh.sh
# Populate ru_government ipset with known Russian government IP ranges.
# Update this list manually or from a trusted external source.
set -euo pipefail

IPSET="ru_government"
ipset create -exist "$IPSET" hash:net
ipset flush "$IPSET"

# Known Russian government/critical infrastructure ranges
# Sources: RIPE NCC, Roskomnadzor BGP announcements
RANGES=(
    "2.18.144.0/20"    # Rostelecom gov
    "5.3.0.0/16"       # Gosuslugi
    "45.11.24.0/22"    # Roskomnadzor
    "77.88.0.0/18"     # Yandex (RU gov portal CDN)
    "213.180.192.0/19" # Yandex
    "185.71.76.0/22"   # mos.ru
    "95.173.128.0/19"  # gosuslugi.ru
)

for cidr in "${RANGES[@]}"; do
    ipset add "$IPSET" "$cidr" 2>/dev/null || true
done

echo "ru_government ipset populated with ${#RANGES[@]} ranges"
