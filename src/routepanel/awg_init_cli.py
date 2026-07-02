# src/routepanel/awg_init_cli.py
"""routepanel-awg-init -- one-time AWG server identity setup (called by the installer).
Usage: routepanel-awg-init --endpoint <public-ip:port> [--subnet 10.8.0.0/24]
       [--port 51820] [--awg-params '{"Jc":"4",...}']"""
import argparse, asyncio, json
from routepanel.config import get_config
from routepanel.db import open_db
from routepanel.settings import get_setting, set_setting
from routepanel import awgserver

async def _run(a) -> None:
    db = await open_db()
    try:
        if await get_setting(db, "awg.private_key"):
            print("AWG server already initialized; refusing to overwrite keys")
            return
        priv, pub = awgserver.gen_keypair()
        for k, v in [("awg.private_key", priv), ("awg.public_key", pub),
                     ("awg.subnet", a.subnet), ("awg.port", str(a.port)),
                     ("awg.endpoint", a.endpoint), ("awg.params", a.awg_params)]:
            await set_setting(db, k, v)
        await db.commit()
        await awgserver.apply_server_conf(db, get_config())
        print(f"AWG server initialized: {a.endpoint}, subnet {a.subnet}")
    finally:
        await db.close()

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", required=True)
    p.add_argument("--subnet", default="10.8.0.0/24")
    p.add_argument("--port", type=int, default=51820)
    p.add_argument("--awg-params", default="{}")
    a = p.parse_args()
    json.loads(a.awg_params)   # fail fast on bad JSON
    asyncio.run(_run(a))
