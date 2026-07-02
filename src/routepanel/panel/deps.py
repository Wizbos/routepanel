# src/routepanel/panel/deps.py
import os, signal
import aiosqlite
from fastapi import Request
from routepanel.db import open_db

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
