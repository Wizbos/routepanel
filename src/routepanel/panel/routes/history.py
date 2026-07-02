# src/routepanel/panel/routes/history.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
import aiosqlite
from routepanel.panel.deps import get_db
from routepanel.panel._templates import templates

router = APIRouter()

@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, db: aiosqlite.Connection = Depends(get_db),
                        action: str = "", limit: int = 200):
    sql = """
        SELECT h.*, dr.name as rule_name
        FROM history h
        LEFT JOIN domain_rules dr ON dr.id = h.domain_rule_id
        WHERE 1=1
    """
    params: list = []
    if action:
        sql += " AND h.action=?"
        params.append(action)
    sql += " ORDER BY h.ts DESC LIMIT ?"
    params.append(limit)
    async with db.execute(sql, params) as cur:
        entries = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "history.html", {
        "request": request, "entries": entries,
        "action_filter": action, "active": "history"
    })
