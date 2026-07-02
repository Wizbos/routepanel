# src/routepanel/panel/routes/exits.py
import os
import sqlite3
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import aiosqlite
from routepanel import awg
from routepanel.config import get_config
from routepanel.panel.deps import get_db, get_actor_ip, trigger_sync
from routepanel.panel._templates import templates
from routepanel.syncd.health import HealthStatus

router = APIRouter()

class ExitIn(BaseModel):
    id: str
    interface: str
    fwmark: int = 0
    routing_table: str = "main"
    health_check_ip: str = "1.1.1.1"
    fallback_exit_id: str | None = None
    priority: int = 0

@router.get("/exits", response_class=HTMLResponse)
async def exits_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT e.*, h.status AS health_status, h.latency_ms AS hlat, h.checked_at AS hchecked "
        "FROM exits e LEFT JOIN exit_health h ON h.exit_id = e.id ORDER BY e.priority"
    ) as cur:
        exits = [dict(r) for r in await cur.fetchall()]
    # Health is written to the DB by routesyncd's health loop (cross-process).
    for e in exits:
        e["health_status"] = e.get("health_status") or "unknown"
        lat = e.get("hlat")
        e["latency_ms"] = f"{lat:.0f}ms" if lat is not None else "-"
    return templates.TemplateResponse(request, "exits.html", {"request": request, "exits": exits, "active": "exits"})

@router.post("/exits")
async def add_exit(data: ExitIn, db: aiosqlite.Connection = Depends(get_db),
                   actor: str = Depends(get_actor_ip)):
    if data.fwmark != 0 and data.routing_table in {"main", "local", "default"}:
        raise HTTPException(
            422, "A non-direct exit (fwmark != 0) must use a dedicated routing table, "
                 "not 'main' -- that would hijack the host's default route.")
    await db.execute(
        "INSERT INTO exits(id,interface,fwmark,routing_table,health_check_ip,fallback_exit_id,priority) VALUES(?,?,?,?,?,?,?)",
        (data.id, data.interface, data.fwmark, data.routing_table,
         data.health_check_ip, data.fallback_exit_id, data.priority)
    )
    await db.execute("INSERT INTO history(action,exit_id,detail,actor_ip) VALUES(?,?,?,?)",
                     ("added", data.id, f"new exit: {data.interface} fwmark={data.fwmark}", actor))
    await db.commit()
    trigger_sync()   # reconcile iptables/ip rules for the new exit immediately
    return {"ok": True}

@router.delete("/exits/{exit_id}")
async def delete_exit(exit_id: str, db: aiosqlite.Connection = Depends(get_db),
                      actor: str = Depends(get_actor_ip)):
    # Refuse to delete an exit still referenced by a rule or another exit's
    # fallback chain -- otherwise the FK throws an opaque 500 and chains orphan.
    async with db.execute(
        "SELECT name FROM domain_rules WHERE exit_id=? OR fallback_override_id=?",
        (exit_id, exit_id)
    ) as cur:
        used_by = [r["name"] for r in await cur.fetchall()]
    async with db.execute(
        "SELECT id FROM exits WHERE fallback_exit_id=?", (exit_id,)
    ) as cur:
        used_by += [f"exit:{r['id']}" for r in await cur.fetchall()]
    if used_by:
        raise HTTPException(409, f"Exit '{exit_id}' is still referenced by: {', '.join(used_by)}")
    await db.execute("DELETE FROM exits WHERE id=?", (exit_id,))
    await db.execute("INSERT INTO history(action,exit_id,detail,actor_ip) VALUES(?,?,?,?)",
                     ("removed", exit_id, "exit deleted", actor))
    await db.commit()
    trigger_sync()   # rebuild the ROUTEPANEL chain without the deleted exit
    return {"ok": True}

class ExitImportIn(BaseModel):
    id: str
    conf_text: str
    health_check_ip: str = "1.1.1.1"

@router.post("/exits/import")
async def import_exit(data: ExitImportIn, db: aiosqlite.Connection = Depends(get_db),
                      actor: str = Depends(get_actor_ip)):
    try:
        tc = awg.parse_tunnel_conf(data.conf_text)
    except awg.ConfError as e:
        raise HTTPException(422, f"config not accepted: {e}")
    async with db.execute("SELECT 1 FROM exits WHERE id=?", (data.id,)) as cur:
        if await cur.fetchone():
            raise HTTPException(422, f"exit '{data.id}' already exists")

    async with db.execute("SELECT COALESCE(MAX(fwmark), 99) + 1 AS next FROM exits") as cur:
        fwmark = (await cur.fetchone())["next"]
    interface = f"rpx{fwmark}"

    try:
        await db.execute(
            "INSERT INTO exits(id,interface,fwmark,routing_table,health_check_ip,type) VALUES(?,?,?,?,?,?)",
            (data.id, interface, fwmark, str(fwmark), data.health_check_ip, "awg"))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "a concurrent import allocated the same fwmark -- retry")

    cfg = get_config()
    os.makedirs(cfg.exit_conf_dir, exist_ok=True)
    conf_path = os.path.join(cfg.exit_conf_dir, f"{interface}.conf")
    fd = os.open(conf_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(awg.render_exit_conf(tc))

    # First imported exit becomes the catch-all default -- announce it loudly.
    cur = await db.execute(
        "INSERT INTO settings(key, value) VALUES('default_exit_id', ?) "
        "ON CONFLICT(key) DO NOTHING", (data.id,))
    is_default = cur.rowcount == 1
    if is_default:
        await db.execute("INSERT INTO history(action,exit_id,detail,actor_ip) VALUES(?,?,?,?)",
                         ("policy", data.id,
                          f"default routing policy: ALL client traffic now routes via '{data.id}'", actor))
    await db.execute("INSERT INTO history(action,exit_id,detail,actor_ip) VALUES(?,?,?,?)",
                     ("added", data.id,
                      f"imported {'AWG' if tc.is_awg else 'WG'} exit: {interface} fwmark={fwmark}", actor))
    await db.commit()
    trigger_sync()
    return {"ok": True, "interface": interface, "fwmark": fwmark, "default": is_default}
