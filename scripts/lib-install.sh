#!/bin/bash
# scripts/lib-install.sh — shared installer helpers (sourced, not executed).
PREFIX="/opt/routepanel"
CONFDIR="/etc/routepanel"
CONFIG="$CONFDIR/config.yaml"

c_ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
c_info() { printf '\033[36m•\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }

die() { c_err "$*"; exit 1; }

require_root() { [[ $EUID -eq 0 ]] || die "run as root (sudo bash install.sh)"; }

check_os() {
    [[ -r /etc/os-release ]] || die "unsupported OS (no /etc/os-release)"
    . /etc/os-release
    case "$ID:$VERSION_ID" in
        ubuntu:22.04|ubuntu:24.04) c_ok "OS $PRETTY_NAME supported" ;;
        *) die "unsupported OS '$PRETTY_NAME' — need Ubuntu 22.04 or 24.04 (Debian support planned)" ;;
    esac
}

detect_wan_iface() { ip route show default 2>/dev/null | awk '/default/{print $5; exit}'; }
detect_public_ip() { curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true; }
detect_ssh_port()  { ss -tlnp 2>/dev/null | awk '/sshd/{split($4,a,":"); print a[length(a)]; exit}'; }

# Never lock the operator out: allow the live SSH port before any other change.
protect_ssh() {
    local p="${1:-22}"
    iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null \
        || iptables -I INPUT 1 -p tcp --dport "$p" -j ACCEPT
    c_ok "SSH port $p kept open"
}

ask() {   # ask "prompt" "default" -> echoes answer (default if no tty)
    local prompt="$1" def="$2" ans
    if [[ ! -r /dev/tty ]]; then echo "$def"; return; fi
    read -r -p "$prompt [$def]: " ans </dev/tty || { echo "$def"; return; }
    echo "${ans:-$def}"
}

ask_var() {   # ask_var ENVVAR "prompt" "default" -> env value if set, else prompt/default
    local var="$1" prompt="$2" def="$3"
    if [[ -n "${!var:-}" ]]; then echo "${!var}"; return; fi
    ask "$prompt" "$def"
}

backup_file() { [[ -f "$1" ]] && cp -a "$1" "$1.bak.$(date -u +%Y%m%dT%H%M%SZ)"; }
rand_port() { shuf -i 20000-60000 -n1; }

install_amneziawg() {
    # AmneziaWG is NOT in the stock Ubuntu repos — it ships in the maintainers'
    # PPA and installs as a DKMS kernel module (needs the running kernel's headers
    # + a compiler). Returns 0 if `awg` ends up available, 2 if it could not be
    # installed (caller aborts). Idempotent: a pre-existing `awg` short-circuits.
    command -v awg >/dev/null 2>&1 && return 0
    c_info "Adding the AmneziaWG PPA and building the kernel module (can take a minute)…"
    command -v add-apt-repository >/dev/null 2>&1 \
        || apt-get install -y -qq software-properties-common >/dev/null 2>&1 || true
    add-apt-repository -y ppa:amnezia/ppa >/dev/null 2>&1 || true
    apt-get update -qq || true
    apt-get install -y -qq dkms "linux-headers-$(uname -r)" build-essential >/dev/null 2>&1 || true
    apt-get install -y -qq amneziawg-dkms amneziawg-tools >/dev/null 2>&1 || true
    command -v awg >/dev/null 2>&1 && return 0
    return 2
}
