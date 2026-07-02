# src/routepanel/awgserver.py
"""The client-facing AmneziaWG server: key management, peer IP allocation and
config rendering. Server identity lives in the settings table (awg.* keys);
peers live in the clients table. apply_server_conf() re-renders the interface
config and live-syncs it (awg syncconf) so peer changes don't drop the tunnel."""
import ipaddress, json, logging, os, shlex, shutil, subprocess
import aiosqlite
from routepanel.settings import get_setting

log = logging.getLogger("routepanel")

def _wg_binary() -> str:
    b = shutil.which("awg") or shutil.which("wg")
    if not b:
        raise RuntimeError("neither 'awg' nor 'wg' binary found")
    return b

def gen_keypair() -> tuple[str, str]:
    b = _wg_binary()
    priv = subprocess.run([b, "genkey"], capture_output=True, text=True, check=True).stdout.strip()
    pub = subprocess.run([b, "pubkey"], input=priv, capture_output=True, text=True, check=True).stdout.strip()
    return priv, pub

def gen_psk() -> str:
    return subprocess.run([_wg_binary(), "genpsk"], capture_output=True, text=True, check=True).stdout.strip()

def allocate_client_ip(taken: set[str], subnet: str) -> str:
    net = ipaddress.ip_network(subnet)
    server_ip = _server_ip(subnet)
    for host in net.hosts():
        ip = str(host)
        if ip == server_ip or ip in taken:
            continue
        return ip
    raise RuntimeError(f"subnet {subnet} exhausted")

def _server_ip(subnet: str) -> str:
    return str(next(ipaddress.ip_network(subnet).hosts()))

async def get_server(db: aiosqlite.Connection) -> dict | None:
    priv = await get_setting(db, "awg.private_key")
    if priv is None:
        return None
    return {
        "private_key": priv,
        "public_key": await get_setting(db, "awg.public_key"),
        "subnet": await get_setting(db, "awg.subnet"),
        "port": int(await get_setting(db, "awg.port")),
        "endpoint": await get_setting(db, "awg.endpoint"),
        "params": json.loads(await get_setting(db, "awg.params") or "{}"),
    }

def render_server_conf(server: dict, clients: list[dict]) -> str:
    net = ipaddress.ip_network(server["subnet"])
    lines = ["[Interface]",
             f"PrivateKey = {server['private_key']}",
             f"Address = {_server_ip(server['subnet'])}/{net.prefixlen}",
             f"ListenPort = {server['port']}"]
    lines += [f"{k} = {v}" for k, v in server["params"].items()]
    for c in clients:
        if not c["enabled"]:
            continue
        lines += ["", "[Peer]", f"# {c['name']}",
                  f"PublicKey = {c['public_key']}",
                  f"PresharedKey = {c['psk']}",
                  f"AllowedIPs = {c['address']}/32"]
    return "\n".join(lines) + "\n"

def render_client_conf(server: dict, client: dict) -> str:
    lines = ["[Interface]",
             f"PrivateKey = {client['private_key']}",
             f"Address = {client['address']}/32",
             f"DNS = {_server_ip(server['subnet'])}"]
    lines += [f"{k} = {v}" for k, v in server["params"].items()]
    lines += ["", "[Peer]",
              f"PublicKey = {server['public_key']}",
              f"PresharedKey = {client['psk']}",
              f"Endpoint = {server['endpoint']}",
              "AllowedIPs = 0.0.0.0/0",
              "PersistentKeepalive = 25"]
    return "\n".join(lines) + "\n"

async def apply_server_conf(db: aiosqlite.Connection, cfg) -> None:
    server = await get_server(db)
    if server is None:
        log.warning("AWG server not initialized (routepanel-awg-init); skipping conf apply")
        return
    async with db.execute("SELECT * FROM clients") as cur:
        clients = [dict(r) for r in await cur.fetchall()]
    conf = render_server_conf(server, clients)
    path = cfg.awg_conf_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")            # backup before change
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(conf)
    quick = shutil.which("awg-quick") or shutil.which("wg-quick")
    wg = shutil.which("awg") or shutil.which("wg")
    if quick and wg:
        r = subprocess.run(
            ["bash", "-c",
             f"{shlex.quote(wg)} syncconf {shlex.quote(cfg.awg_interface)} "
             f"<({shlex.quote(quick)} strip {shlex.quote(path)})"],
            capture_output=True, text=True)
        if r.returncode != 0:
            log.error("awg syncconf failed (config written; will apply on iface restart): %s",
                      r.stderr.strip())
