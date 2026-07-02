# src/routepanel/panel/deps.py
import os, signal
import aiosqlite
from fastapi import Request, HTTPException
from routepanel.db import open_db
from routepanel.config import get_config

async def get_db() -> aiosqlite.Connection:
    db = await open_db()
    try:
        yield db
    finally:
        await db.close()

def get_actor_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

def trigger_sync() -> None:
    """Signal routesyncd (SIGUSR1) to run an immediate sync. Shared by the
    domains and exits routers so panel edits apply without waiting for the
    5-minute poll."""
    pid_file = "/run/routesyncd.pid"
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                os.kill(int(f.read().strip()), signal.SIGUSR1)
        except (ProcessLookupError, ValueError, FileNotFoundError):
            pass

def check_auth(request: Request) -> None:
    """Optional defence-in-depth (spec §12). No-op unless `auth_token` is set in
    config. To enable for the JSON API, add `dependencies=[Depends(check_auth)]`
    to the routers; a browser-login flow for the HTML UI is out of scope for v1."""
    cfg = get_config()
    if not cfg.auth_token:
        return
    token = request.headers.get("X-Auth-Token") or request.cookies.get("rp_token")
    if token != cfg.auth_token:
        raise HTTPException(401, "unauthorized")
