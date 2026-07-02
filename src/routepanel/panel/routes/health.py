# src/routepanel/panel/routes/health.py
import os
from fastapi import APIRouter, Depends
import aiosqlite
from routepanel.panel.deps import get_db

router = APIRouter()

def _syncd_alive() -> bool:
    try:
        with open("/run/routesyncd.pid") as f:
            os.kill(int(f.read().strip()), 0)
        return True
    except (OSError, ValueError):
        return False

@router.get("/health")
async def health(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT e.id, COALESCE(h.status,'unknown') AS status, h.latency_ms, h.checked_at "
        "FROM exits e LEFT JOIN exit_health h ON h.exit_id = e.id ORDER BY e.id"
    ) as cur:
        exits = [dict(r) for r in await cur.fetchall()]
    return {"status": "ok", "exits": exits, "syncd_alive": _syncd_alive()}
