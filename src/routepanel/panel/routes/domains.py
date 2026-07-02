# src/routepanel/panel/routes/domains.py
import json
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import aiosqlite
from routepanel.panel.deps import get_db, get_actor_ip, trigger_sync
from routepanel.panel._templates import templates
from routepanel.cidr import normalize_cidrs

router = APIRouter()

class DomainRuleIn(BaseModel):
    name: str
    domains: list[str]
    exit_id: str
    fallback_override_id: str | None = None
    ospf_distribute: bool = False
    static_cidrs: list[str] = []          # stable prefixes -> rule ipset + OSPF (corp routing)
    notes: str | None = None

class DomainRuleUpdate(DomainRuleIn):
    pass

@router.get("/", response_class=HTMLResponse)
async def domains_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    # All rules; filtering/sorting is done client-side in table.js.
    # exit_health mirrors routes/exits.py: written cross-process by routesyncd.
    sql = """
        SELECT dr.*,
               COUNT(ri.id) AS ip_count,
               MAX(ri.last_seen) AS last_sync,
               h.status AS exit_health
        FROM domain_rules dr
        LEFT JOIN resolved_ips ri ON ri.domain_rule_id = dr.id
        LEFT JOIN exit_health h ON h.exit_id = dr.exit_id
        GROUP BY dr.id
        ORDER BY dr.name COLLATE NOCASE
    """
    async with db.execute(sql) as cur:
        rules = [dict(r) for r in await cur.fetchall()]
    for r in rules:
        r["domains_list"] = json.loads(r["domains"])
        r["cidrs_list"] = json.loads(r["static_cidrs"] or "[]")
        r["exit_health"] = r.get("exit_health") or "unknown"
    async with db.execute("SELECT id FROM exits ORDER BY priority") as cur:
        exits = [dict(e) for e in await cur.fetchall()]
    async with db.execute("SELECT * FROM service_library ORDER BY name") as cur:
        library = [dict(l) for l in await cur.fetchall()]
    for l in library:
        l["domains_list"] = json.loads(l["domains"])
        l["cidrs_list"] = json.loads(l["cidrs"] or "[]")
    return templates.TemplateResponse(request, "domains.html", {
        "request": request, "rules": rules, "exits": exits,
        "library": library, "active": "domains",
    })

@router.post("/domains")
async def add_domain_rule(data: DomainRuleIn, db: aiosqlite.Connection = Depends(get_db),
                           actor: str = Depends(get_actor_ip)):
    async with db.execute("SELECT id FROM exits WHERE id=?", (data.exit_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(400, f"Exit '{data.exit_id}' not found")
    try:
        static_cidrs = normalize_cidrs(data.static_cidrs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.execute(
        "INSERT INTO domain_rules(name,domains,exit_id,fallback_override_id,ospf_distribute,static_cidrs,notes) VALUES(?,?,?,?,?,?,?)",
        (data.name, json.dumps(data.domains), data.exit_id,
         data.fallback_override_id, int(data.ospf_distribute),
         json.dumps(static_cidrs), data.notes)
    )
    await db.execute(
        "INSERT INTO history(action,exit_id,detail,actor_ip) VALUES(?,?,?,?)",
        ("added", data.exit_id, f"added rule: {data.name}", actor)
    )
    await db.commit()
    trigger_sync()
    return {"ok": True}

@router.put("/domains/{rule_id}")
async def update_domain_rule(rule_id: int, data: DomainRuleUpdate,
                             db: aiosqlite.Connection = Depends(get_db),
                             actor: str = Depends(get_actor_ip)):
    async with db.execute("SELECT id FROM domain_rules WHERE id=?", (rule_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Rule not found")
    async with db.execute("SELECT id FROM exits WHERE id=?", (data.exit_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(400, f"Exit '{data.exit_id}' not found")
    try:
        static_cidrs = normalize_cidrs(data.static_cidrs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.execute(
        """UPDATE domain_rules SET name=?, domains=?, exit_id=?, fallback_override_id=?,
                  ospf_distribute=?, static_cidrs=?, notes=?, updated_at=datetime('now') WHERE id=?""",
        (data.name, json.dumps(data.domains), data.exit_id, data.fallback_override_id,
         int(data.ospf_distribute), json.dumps(static_cidrs), data.notes, rule_id)
    )
    await db.execute(
        "INSERT INTO history(action,domain_rule_id,exit_id,detail,actor_ip) VALUES(?,?,?,?,?)",
        ("changed", rule_id, data.exit_id, f"edited rule: {data.name}", actor)
    )
    await db.commit()
    trigger_sync()
    return {"ok": True}

@router.delete("/domains/{rule_id}")
async def delete_domain_rule(rule_id: int, db: aiosqlite.Connection = Depends(get_db),
                              actor: str = Depends(get_actor_ip)):
    async with db.execute("SELECT name, exit_id FROM domain_rules WHERE id=?", (rule_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Rule not found")
    await db.execute("DELETE FROM domain_rules WHERE id=?", (rule_id,))
    await db.execute(
        "INSERT INTO history(action,exit_id,detail,actor_ip) VALUES(?,?,?,?)",
        ("removed", row["exit_id"], f"removed rule: {row['name']}", actor)
    )
    await db.commit()
    trigger_sync()
    return {"ok": True}
