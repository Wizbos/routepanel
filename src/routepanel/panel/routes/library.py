# src/routepanel/panel/routes/library.py
import json
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import aiosqlite
from routepanel.panel.deps import get_db
from routepanel.panel._templates import templates
from routepanel.cidr import normalize_cidrs

router = APIRouter()

class PackIn(BaseModel):
    id: str
    name: str
    domains: list[str]
    cidrs: list[str] = []

class PackUpdate(BaseModel):
    name: str
    domains: list[str]
    cidrs: list[str] = []

class CidrsUpdate(BaseModel):
    cidrs: list[str]

@router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM service_library ORDER BY name") as cur:
        packs = [dict(r) for r in await cur.fetchall()]
    for p in packs:
        p["domains_list"] = json.loads(p["domains"])
        p["cidrs_list"] = json.loads(p["cidrs"] or "[]")
    return templates.TemplateResponse(request, "library.html", {"request": request, "packs": packs, "active": "library"})

@router.post("/library")
async def add_pack(data: PackIn, db: aiosqlite.Connection = Depends(get_db)):
    try:
        cidrs = normalize_cidrs(data.cidrs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.execute(
        "INSERT OR REPLACE INTO service_library(id, name, domains, cidrs) VALUES(?,?,?,?)",
        (data.id, data.name, json.dumps(data.domains), json.dumps(cidrs))
    )
    await db.commit()
    return {"ok": True}

@router.put("/library/{pack_id}")
async def update_pack(pack_id: str, data: PackUpdate, db: aiosqlite.Connection = Depends(get_db)):
    try:
        cidrs = normalize_cidrs(data.cidrs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.execute(
        "UPDATE service_library SET name=?, domains=?, cidrs=?, updated_at=datetime('now') WHERE id=?",
        (data.name, json.dumps(data.domains), json.dumps(cidrs), pack_id)
    )
    await db.commit()
    return {"ok": True}

@router.patch("/library/{pack_id}/cidrs")
async def update_pack_cidrs(pack_id: str, data: CidrsUpdate,
                            db: aiosqlite.Connection = Depends(get_db)):
    """Update ONLY a pack's cidrs (domains/name preserved). Used by the weekly
    google-cidr-refresh job so it doesn't have to round-trip the domains list."""
    async with db.execute("SELECT id FROM service_library WHERE id=?", (pack_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, f"Pack '{pack_id}' not found")
    try:
        cidrs = normalize_cidrs(data.cidrs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.execute(
        "UPDATE service_library SET cidrs=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(cidrs), pack_id)
    )
    await db.commit()
    return {"ok": True}

@router.delete("/library/{pack_id}")
async def delete_pack(pack_id: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM service_library WHERE id=?", (pack_id,))
    await db.commit()
    return {"ok": True}
