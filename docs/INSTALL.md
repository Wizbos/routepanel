# Installing routepanel

This is the long-form install reference. For the short version see the
[Quick start](../README.md#quick-start) in the README.

## Supported OS

The installer checks `/etc/os-release` and refuses to run anywhere else:

- Ubuntu 22.04 LTS
- Ubuntu 24.04 LTS
- Debian 12 ("bookworm")

It is IPv4-only end to end — AAAA answers are suppressed for routed domains
by design, as a deliberate leak-prevention measure, not a gap to be filled
later.

## Running the installer

On a fresh VPS, as root:

```bash
apt-get install -y git
git clone https://github.com/Wizbos/routepanel && cd routepanel
sudo bash install.sh
```

`install.sh` checks whether `/etc/routepanel/config.yaml` already exists. If
it doesn't, you get the **first-run wizard**; if it does, you get the
**management menu** instead (see below) — so `sudo bash install.sh` is also
the correct command to re-run later.

### First-run wizard

The wizard, in order:

1. **OS check** — verifies Ubuntu 22.04/24.04 or Debian 12, aborts otherwise.
2. **SSH-port protection** — detects the live `sshd` port and inserts an
   `iptables` ACCEPT rule for it *before* touching anything else, so a
   half-finished install can never lock you out over SSH.
3. **Prompts** — AmneziaWG UDP port (random default), client tunnel subnet
   (default `10.8.0.0/24`), first client (device) name, panel password
   (blank = auto-generated and printed), and whether to route known Russian
   networks direct (RU-direct, default yes).
4. **Packages** — installs `python3-venv`, `iptables`, `ipset`, `dnsmasq`,
   `dnscrypt-proxy`, `wireguard-tools`, etc., then AmneziaWG: it tries the
   `amneziawg-dkms` kernel module first and falls back to the userspace
   `amneziawg-go` daemon if DKMS isn't available for the running kernel.
5. **Install layout** — copies the code to `/opt/routepanel`, creates a
   Python venv at `/opt/routepanel/.venv`, and installs the package into it.
6. **Config + secrets** — writes `/etc/routepanel/config.yaml` from
   `config.yaml.example`, patched with the detected WAN interface and your
   RU-direct choice; creates `/etc/routepanel/db.sqlite` at mode `0600`;
   generates the AmneziaWG server identity (`routepanel-awg-init`) and sets
   the panel password (`routepanel-passwd`), also stored at mode `0600`.
7. **DNS chain** — runs `scripts/setup-dns.sh` to wire up dnsmasq and
   dnscrypt-proxy (see below).
8. **systemd units** — installs and enables `routepanel-init`, `routepanel`,
   `routesyncd`, and (if RU-direct is on) `ru-direct-refresh.timer`; brings
   up `awg-quick@<iface>` for the AmneziaWG interface.
9. **First client** — creates the client you named in step 3, and prints its
   config as a QR code directly in the terminal (plus the raw text, also
   available later from the panel).
10. **Summary** — announces the default routing policy (see the README), and
    prints the `ssh -L` line and panel password so you can log in right away.

### Re-run: the management menu

Once `/etc/routepanel/config.yaml` exists, `sudo bash install.sh` (equivalently
`scripts/menu.sh`) shows a menu instead of re-running the wizard:

1. **Service status** — `systemctl status` for `routepanel`, `routesyncd`,
   `routepanel-init`.
2. **Show panel access** — reprints the `ssh -L` line for the current VPS IP.
3. **Create emergency client** — adds a new client and prints its QR/config,
   for when you're locked out of the panel itself but still have SSH.
4. **Change panel password** — re-runs `routepanel-passwd` interactively.
5. **Toggle RU-direct routing** — flips `ru_direct` in `config.yaml`, enables
   or disables the weekly refresh timer, and restarts `routesyncd` to apply.
6. **Update routepanel** — see "Updating" below.
7. **Uninstall** — requires typing `UNINSTALL` to confirm, then runs
   `scripts/uninstall.sh`.
0. **Quit**.

## Install layout

| What | Where |
|---|---|
| Application code + venv | `/opt/routepanel` (venv at `/opt/routepanel/.venv`) |
| Config, DB, keys, exit configs | `/etc/routepanel` |
| Main config file | `/etc/routepanel/config.yaml` |
| SQLite database (mode `0600`) | `/etc/routepanel/db.sqlite` |
| Panel password hash (mode `0600`) | `/etc/routepanel/panel.passwd` |
| Imported exit-node tunnel configs | `/etc/routepanel/exits/` |
| systemd units | `/etc/systemd/system/routepanel*.service`, `routesyncd.service`, `ru-direct-refresh.{service,timer}` |

## systemd units

- **`routepanel-init.service`** — a oneshot that sets up ip rules, ipsets,
  and iptables chains at boot, before the panel or sync daemon start. It
  tolerates AmneziaWG not being up yet, so it no longer hard-orders after
  `awg-quick@*`; the wizard brings up `awg-quick@<iface>` first regardless.
- **`routepanel.service`** — the web panel itself (`routepanel` entry point),
  bound to `127.0.0.1:8080` by default. Requires `routepanel-init.service`.
- **`routesyncd.service`** — the polling daemon that reconciles routing
  rules, health-checks exit nodes, and applies DNS/ipset state. Requires
  `routepanel-init.service`, wants `dnsmasq.service`.
- **`ru-direct-refresh.service` + `.timer`** — oneshot + weekly timer that
  refresh the `ru_direct` ipset (see below). Only enabled if you turned
  RU-direct on.

## The DNS chain

Client DNS queries to the AmneziaWG server's port 53 are DNAT'd to a local
resolver chain:

```
client :53  --DNAT-->  dnsmasq 127.0.0.1:5353  --forwards-->  dnscrypt-proxy 127.0.0.1:5054
```

- **dnsmasq** (`127.0.0.1:5353`) does the actual resolution-as-marking: as it
  answers a query for a domain in a routed service pack, it tags the
  resolved IP into that pack's ipset, so `iptables` fwmarks match the traffic
  the client is about to send. This is what "DNS consistency by design" in
  the README refers to — the ipset a client's traffic hits is always fed by
  the same resolver the client used.
- **dnscrypt-proxy** (`127.0.0.1:5054`) is the actual upstream resolver,
  using DoH (Cloudflare/Google by default) so upstream DNS isn't trivially
  visible to the VPS's provider or network.
- Because the DNAT rewrites the destination to loopback, the installer
  persists `net.ipv4.conf.all.route_localnet = 1` — without it the kernel
  silently drops packets DNAT'd to `127.0.0.1` that arrive from a
  non-loopback interface (i.e. from the AmneziaWG tunnel).

`scripts/setup-dns.sh` installs the base dnsmasq config
(`/etc/dnsmasq.d/routepanel-base.conf`), creates the daemon-managed
`/etc/routepanel/dnsmasq-routepanel.conf` (regenerated by `routesyncd` as
routing rules change), and writes a minimal `dnscrypt-proxy.toml`.

## RU-direct

If enabled (installer prompt, or menu item 5 later), known Russian IPv4
networks bypass exit-node tunneling and go direct from the VPS's own IP —
useful for domestic banks, government portals, and other RU-only services
that don't tunnel well or don't need to.

- Source: the aggregated RU zone from
  `https://www.ipdeny.com/ipblocks/data/aggregated/ru-aggregated.zone`
  (configurable via `ru_direct_url` in `config.yaml`).
- `scripts/ru_direct_refresh.py` fetches and parses the zone, then swaps it
  into the `ru_direct` ipset atomically (`ipset swap`) so the routing chain
  never observes an empty or half-populated set. A failed fetch/parse keeps
  the existing set rather than clearing it.
- `ru-direct-refresh.timer` runs this weekly; the installer also runs it
  once immediately if you opt in.
- Toggle any time from the management menu (option 5) — this flips
  `ru_direct` in `config.yaml`, enables/disables the timer, and restarts
  `routesyncd`.

## Adding exit nodes

Exit nodes are WireGuard/AmneziaWG tunnels to other VPNs that routed traffic
egresses through. In v1, import one by pasting its config via the exit API —
configs land in `/etc/routepanel/exits/`. (A paste-in-panel exit-node screen
is planned but not built yet; see the deferred-work list below.) The
installer does not create any exit nodes for you: with none configured, all
client traffic goes direct from the VPS's own IP (see the README's *Default
routing policy*), and health checks / failover chains only apply once you've
added at least one.

## Panel access

The panel binds to `127.0.0.1:8080` only — it is never exposed on a public
interface. Reach it over an SSH local-port-forward:

```bash
ssh -L 8080:localhost:8080 root@<vps-ip>
```

then browse `http://localhost:8080`. Password auth is always required (set
during install, changeable from the menu or via `routepanel-passwd`).
"Show panel access" in the management menu reprints this line with the
current detected public IP.

## Updating

From the management menu, option 6 ("Update routepanel"):

- If `/opt/routepanel` is a git checkout (the normal case, since the
  installer clones the repo and copies from it in place), this runs
  `git pull --ff-only`, reinstalls the package into the venv, and restarts
  `routepanel` and `routesyncd`.
- If it isn't a git checkout, the menu prints manual steps: re-clone
  elsewhere and `rsync` into `/opt/routepanel` (excluding `.superpowers` and
  `.venv`), then reinstall and restart the same two services.

## Uninstalling

From the management menu, option 7 (requires typing `UNINSTALL` to confirm),
or directly:

```bash
sudo bash scripts/uninstall.sh [--purge]
```

This stops and disables `routepanel`, `routesyncd`, `routepanel-init`, and
`ru-direct-refresh.timer`, and removes their unit files. By default
`/etc/routepanel` (config, database, WireGuard keys) is left in place. With
`--purge`, it is **archived**, not deleted — moved to
`/etc/routepanel.removed-<UTC-timestamp>` — so keys and history are always
recoverable. Application code at `/opt/routepanel` is never removed
automatically; delete it by hand if you want it gone.

## Scope and what's deferred

This installer covers the whole Plan 2 surface: OS/SSH checks, package and
AmneziaWG install, config/DB/secrets bootstrap, the DNS chain, RU-direct,
systemd units, first-client QR, and the re-run management menu (status,
access, emergency client, password, RU-direct toggle, update, uninstall).

Not covered here, deferred to a later release:

- **VLESS/Xray exit nodes** — schema is ready, import UI is not built yet.
- **Advanced OSPF menu module** — OSPF advertisement itself works (see the
  README's Features list); a dedicated install/menu workflow for it, plus a
  documented Pi-hole/AdGuard recipe, is planned for `docs/advanced.md`.
- **Fresh-VPS release checklist** and a published, tagged `Wizbos/routepanel`
  release.

If you hit an OS or environment this installer doesn't handle, open an issue
rather than hand-patching `/etc/routepanel` — the goal is that everything
here stays reproducible from `install.sh`.
