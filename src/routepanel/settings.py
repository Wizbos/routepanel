# src/routepanel/settings.py
import aiosqlite

async def get_setting(db: aiosqlite.Connection, key: str) -> str | None:
    async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    return row["value"] if row else None

async def set_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

async def get_default_exit_id(db: aiosqlite.Connection, cfg) -> str:
    """Default catch-all exit: DB setting wins (panel-controlled), then config,
    then 'direct'. 'direct' resolves to fwmark 0 even if no such exit row exists."""
    return (await get_setting(db, "default_exit_id")) or cfg.default_exit_id or "direct"
