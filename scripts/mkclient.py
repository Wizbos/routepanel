#!/usr/bin/env python3
"""scripts/mkclient.py — create a routepanel client by name, print its QR + conf.

Reusable version of the client-creation logic used inline by install.sh's
first-run wizard (Task 5) and by scripts/menu.sh's "emergency client" action
(Task 6). Requires ROUTEPANEL_CONFIG to point at the active config.yaml.

Usage:
    python3 scripts/mkclient.py <client-name>
"""
import asyncio
import sys

from routepanel.config import get_config
from routepanel.db import open_db
from routepanel import awgserver

try:
    import qrcode
except ImportError:
    qrcode = None


async def create_client(name: str) -> int:
    """Create a client named `name`, apply the new server conf, return its id."""
    db = await open_db()
    try:
        srv = await awgserver.get_server(db)
        async with db.execute("SELECT address FROM clients") as c:
            taken = {r["address"] for r in await c.fetchall()}
        ip = awgserver.allocate_client_ip(taken, srv["subnet"])
        priv, pub = awgserver.gen_keypair()
        psk = awgserver.gen_psk()
        cur = await db.execute(
            "INSERT INTO clients(name,public_key,private_key,psk,address) VALUES(?,?,?,?,?)",
            (name, pub, priv, psk, ip),
        )
        await db.commit()
        await awgserver.apply_server_conf(db, get_config())
        return cur.lastrowid
    finally:
        await db.close()


async def print_client(cid: int) -> None:
    """Print the QR code (if qrcode is installed) and raw conf for client `cid`."""
    db = await open_db()
    try:
        srv = await awgserver.get_server(db)
        async with db.execute("SELECT * FROM clients WHERE id=?", (cid,)) as c:
            row = await c.fetchone()
        cl = dict(row)
    finally:
        await db.close()
    conf = awgserver.render_client_conf(srv, cl)
    if qrcode:
        q = qrcode.QRCode(border=1)
        q.add_data(conf)
        q.make()
        q.print_ascii(invert=True)
    print("\n--- client config (also available in the panel) ---\n" + conf)


async def main(name: str) -> None:
    cid = await create_client(name)
    await print_client(cid)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: mkclient.py <client-name>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
