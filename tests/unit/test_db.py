# tests/unit/test_db.py
import pytest, aiosqlite, json
from routepanel.db import open_db

@pytest.mark.asyncio
async def test_schema_creates_all_tables(tmp_db):
    async with tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        tables = {r[0] for r in await cur.fetchall()}
    assert {"exits", "domain_rules", "resolved_ips", "history", "service_library"} <= tables

@pytest.mark.asyncio
async def test_exits_fk_enforced(tmp_db):
    await tmp_db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(Exception):
        await tmp_db.execute(
            "INSERT INTO domain_rules (name, domains, exit_id) VALUES (?,?,?)",
            ("test", '["x.com"]', "nonexistent")
        )
        await tmp_db.commit()
