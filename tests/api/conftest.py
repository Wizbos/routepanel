# tests/api/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from routepanel.panel.app import app
from routepanel.db import open_db
from routepanel.config import get_config, reset_config
import os

@pytest.fixture
async def test_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("ROUTEPANEL_CONFIG", "")
    reset_config()
    # override db path in open_db via monkeypatching get_config
    from routepanel import config as cfg_mod
    cfg_mod._config = cfg_mod.Config(db_path=db_path)

    db = await open_db(db_path)
    # seed exits
    await db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES(?,?,?,?)",
                     ("doprax","awg1",100,"vpn"))
    await db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES(?,?,?,?)",
                     ("direct","eth0",0,"main"))
    await db.commit()
    await db.close()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
