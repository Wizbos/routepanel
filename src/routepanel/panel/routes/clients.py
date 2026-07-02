# src/routepanel/panel/routes/clients.py
import io
import logging
import re
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel
import aiosqlite
import qrcode
import qrcode.image.svg
from routepanel import awgserver
from routepanel.config import get_config
from routepanel.panel.deps import get_db, get_actor_ip
from routepanel.panel._templates import templates

router = APIRouter()

log = logging.getLogger("routepanel")
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,63}$")

class ClientIn(BaseModel):
    name: str

async def _require_server(db: aiosqlite.Connection) -> dict:
    server = await awgserver.get_server(db)
    if server is None:
        raise HTTPException(503, "AWG server not initialized -- run routepanel-awg-init first")
    return server

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM clients ORDER BY enabled DESC, id") as cur:
        clients = [dict(r) for r in await cur.fetchall()]
    server = await awgserver.get_server(db)
    return templates.TemplateResponse(request, "clients.html",
        {"request": request, "clients": clients, "server": server, "active": "clients"})

@router.post("/clients")
async def add_client(data: ClientIn, db: aiosqlite.Connection = Depends(get_db),
                     actor: str = Depends(get_actor_ip)):
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "client name required")
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(422, "client name must be 1-63 chars: letters, digits, dot, dash, underscore")
    server = await _require_server(db)
    # Only an ACTIVE client with this name blocks reuse -- a revoked client's
    # name is free to reissue (matches idx_clients_active_name).
    async with db.execute("SELECT 1 FROM clients WHERE name=? AND enabled=1", (name,)) as cur:
        if await cur.fetchone():
            raise HTTPException(422, f"client '{name}' already exists")
    async with db.execute("SELECT address FROM clients") as cur:
        taken = {r["address"] for r in await cur.fetchall()}
    address = awgserver.allocate_client_ip(taken, server["subnet"])
    priv, pub = awgserver.gen_keypair()
    psk = awgserver.gen_psk()
    cur = await db.execute(
        "INSERT INTO clients(name, public_key, private_key, psk, address) VALUES(?,?,?,?,?)",
        (name, pub, priv, psk, address))
    cid = cur.lastrowid
    await db.execute("INSERT INTO history(action,detail,actor_ip) VALUES(?,?,?)",
                     ("added", f"client '{name}' ({address})", actor))
    await db.commit()
    try:
        await awgserver.apply_server_conf(db, get_config())
    except Exception as e:
        # DB change is committed; the conf re-render will happen on the next
        # successful change or interface restart -- do not fail the request.
        log.error("apply_server_conf failed after client change: %s", e)
    return {"ok": True, "id": cid, "address": address}

@router.post("/clients/{client_id}/revoke")
async def revoke_client(client_id: int, db: aiosqlite.Connection = Depends(get_db),
                        actor: str = Depends(get_actor_ip)):
    cur = await db.execute(
        "UPDATE clients SET enabled=0, revoked_at=datetime('now') WHERE id=? AND enabled=1",
        (client_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "client not found or already revoked")
    await db.execute("INSERT INTO history(action,detail,actor_ip) VALUES(?,?,?)",
                     ("removed", f"client {client_id} revoked (kept in DB)", actor))
    await db.commit()
    try:
        await awgserver.apply_server_conf(db, get_config())
    except Exception as e:
        # DB change is committed; the conf re-render will happen on the next
        # successful change or interface restart -- do not fail the request.
        log.error("apply_server_conf failed after client change: %s", e)
    return {"ok": True}

async def _get_active_client(db: aiosqlite.Connection, client_id: int) -> dict:
    async with db.execute("SELECT * FROM clients WHERE id=? AND enabled=1", (client_id,)) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "client not found")
    return dict(row)

@router.get("/clients/{client_id}/conf", response_class=PlainTextResponse)
async def client_conf(client_id: int, db: aiosqlite.Connection = Depends(get_db)):
    server = await _require_server(db)
    client = await _get_active_client(db, client_id)
    return PlainTextResponse(
        awgserver.render_client_conf(server, client),
        headers={"Content-Disposition": f'attachment; filename="{client["name"]}.conf"', "Cache-Control": "no-store"})

@router.get("/clients/{client_id}/qr")
async def client_qr(client_id: int, db: aiosqlite.Connection = Depends(get_db)):
    server = await _require_server(db)
    client = await _get_active_client(db, client_id)
    img = qrcode.make(awgserver.render_client_conf(server, client),
                      image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO(); img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})
