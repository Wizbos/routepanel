import sqlite3
import aiosqlite
import pytest
from routepanel.db import open_db

async def test_exits_type_added_to_legacy_db(tmp_path):
    # simulate a pre-OSS database: exits without `type`
    legacy = str(tmp_path / "legacy.db")
    db = await aiosqlite.connect(legacy)
    await db.execute("CREATE TABLE exits (id TEXT PRIMARY KEY, interface TEXT NOT NULL, "
                     "fwmark INTEGER NOT NULL DEFAULT 0, routing_table TEXT NOT NULL DEFAULT 'main', "
                     "health_check_ip TEXT NOT NULL DEFAULT '1.1.1.1', "
                     "fallback_exit_id TEXT, priority INTEGER NOT NULL DEFAULT 0)")
    await db.execute("INSERT INTO exits(id, interface) VALUES('old', 'awg1')")
    await db.commit(); await db.close()

    db = await open_db(legacy)
    async with db.execute("SELECT type FROM exits WHERE id='old'") as cur:
        row = await cur.fetchone()
    assert row["type"] == "manual"
    await db.close()

async def test_clients_table_exists(tmp_db):
    await tmp_db.execute("INSERT INTO clients(name, public_key, private_key, psk, address) "
                         "VALUES('phone','pub','priv','psk','10.8.0.2')")
    await tmp_db.commit()
    async with tmp_db.execute("SELECT enabled FROM clients WHERE name='phone'") as cur:
        assert (await cur.fetchone())["enabled"] == 1

async def test_unique_fwmark_index(tmp_db):
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES('a','rpx100',100,'100')")
    with pytest.raises(sqlite3.IntegrityError):
        await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES('b','rpx100b',100,'100')")

async def test_fwmark_zero_not_constrained(tmp_db):
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES('d1','eth0',0,'main')")
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES('d2','eth1',0,'main')")
