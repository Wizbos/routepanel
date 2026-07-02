# routepanel

Turn a bare VPS into your personal AmneziaWG gateway with per-service routing:
connect your devices to one server, then route YouTube through one exit VPN,
keep your bank direct, and send Discord through another — controlled from a
small web panel.

## How it works
Your devices connect to the VPS over AmneziaWG (DPI-resistant WireGuard).
On the VPS, dnsmasq resolves your DNS and tags routed domains into ipsets;
iptables fwmarks send matching traffic out **exit nodes** — WireGuard/AmneziaWG
tunnels to other VPNs whose config you import (via the installer or the exit
API). Everything else follows the default policy below.

## Default routing policy
> **All client traffic goes through your first exit node. If you have no exit
> nodes yet, ALL traffic goes direct from the VPS's own IP.** The installer
> prints this at the end of setup, and the panel's History log records the
> policy each time the default changes.
>
> Known Russian networks can be routed direct too (`ru_direct`, offered by the
> installer, kept current by a weekly refresh) — see
> [docs/INSTALL.md](docs/INSTALL.md).

## Quick start
On a fresh Ubuntu 22.04/24.04 or Debian 12 VPS, as root:

    apt-get install -y git
    git clone https://github.com/Wizbos/routepanel && cd routepanel
    sudo bash install.sh

The wizard asks for the AWG port, client subnet, first device name, panel
password, and whether to route RU networks direct — then prints your first
client's QR code and the `ssh -L` line to reach the panel. Re-run
`sudo bash install.sh` any time for the management menu (status, show
access, emergency client, change password, toggle RU-direct, update,
uninstall).

See [docs/INSTALL.md](docs/INSTALL.md) for the full install reference.

## Features
- Interactive installer (Ubuntu 22.04/24.04, Debian 12): first-run wizard,
  then a re-run management menu (status, access, emergency client, password,
  RU-direct toggle, git-aware update, uninstall)
- Client management in the panel: add a device, scan a QR, done
- Exit nodes from pasted WireGuard/AmneziaWG configs, with health checks and failover chains
- Per-service routing rules with a seeded library (YouTube, Telegram, Meta, Discord, …)
- DNS consistency by design: resolution = marking (dnsmasq feeds the ipsets clients actually use)
- Known Russian networks routed direct on request, refreshed weekly from an aggregated RU zone feed
- `/health` JSON endpoint
- Advanced: OSPF advertisement of routed prefixes into your own network (FRR)

## Security model
- Panel binds to `127.0.0.1:8080` by default — access it via `ssh -L 8080:localhost:8080 root@vps`
- Password auth is always on (set by the installer / `routepanel-passwd`)
- The installer never touches your default route and always allows the SSH port first

## Not in v1.0
IPv6 (AAAA is suppressed for routed domains — deliberate leak prevention) ·
VLESS/Xray exits (planned; schema ready) · advanced OSPF menu module ·
Pi-hole/AdGuard multi-site sync (documented recipe only) · Prometheus
metrics · multi-user panel.

## Status & support
This is a free-time project, provided **as is**. Further development is likely
but not promised. Suggestions and PRs are welcome — especially service-library
packs.

## License
MIT
