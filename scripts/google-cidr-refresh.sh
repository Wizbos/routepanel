#!/bin/bash
# scripts/google-cidr-refresh.sh
# Fetch Google's published ranges and update the youtube + google library packs'
# CIDRs via the PATCH /library/{id}/cidrs endpoint (domains/name preserved).
set -euo pipefail
API="http://127.0.0.1:8080"
CIDRS=$(curl -fsSL https://www.gstatic.com/ipranges/goog.json \
  | python3 -c "import json,sys; print(json.dumps([p['ipv4Prefix'] for p in json.load(sys.stdin)['prefixes'] if 'ipv4Prefix' in p]))")
for pack in youtube google; do
  curl -fsS -X PATCH "$API/library/$pack/cidrs" -H 'Content-Type: application/json' \
    -d "{\"cidrs\":$CIDRS}" >/dev/null || echo "WARN: PATCH $pack failed"
done
echo "google/youtube CIDRs refreshed ($(echo "$CIDRS" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))') prefixes)"
