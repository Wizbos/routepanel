import pytest
from routepanel.settings import get_setting
from routepanel.db import open_db

CONF = """
[Interface]
PrivateKey = aBcD+priv=
Address = 10.66.0.2/32

[Peer]
PublicKey = eFgH+pub=
Endpoint = 203.0.113.10:51820
AllowedIPs = 0.0.0.0/0
"""

@pytest.fixture
async def import_env(tmp_path, test_client):
    from routepanel import config as cfg_mod
    cfg_mod._config.exit_conf_dir = str(tmp_path / "exits")
    return test_client

async def test_import_creates_exit_and_conf(import_env, tmp_path):
    r = await import_env.post("/exits/import", json={"id": "myvpn", "conf_text": CONF})
    assert r.status_code == 200
    body = r.json()
    assert body["fwmark"] == 101          # conftest seeds doprax at fwmark 100
    assert body["interface"] == "rpx101"
    conf = (tmp_path / "exits" / "rpx101.conf").read_text()
    assert "Table = off" in conf

async def test_first_import_sets_default(import_env):
    # conftest's seeded DB has no settings row -> first import claims default
    r = await import_env.post("/exits/import", json={"id": "first", "conf_text": CONF})
    assert r.json()["default"] is True
    r2 = await import_env.post("/exits/import", json={"id": "second", "conf_text": CONF})
    assert r2.json()["default"] is False

async def test_import_bad_conf_422(import_env):
    r = await import_env.post("/exits/import", json={"id": "bad", "conf_text": "garbage"})
    assert r.status_code == 422

async def test_import_duplicate_id_422(import_env):
    await import_env.post("/exits/import", json={"id": "dup", "conf_text": CONF})
    r = await import_env.post("/exits/import", json={"id": "dup", "conf_text": CONF})
    assert r.status_code == 422

async def test_delete_default_exit_409(import_env):
    r = await import_env.post("/exits/import", json={"id": "myvpn", "conf_text": CONF})
    assert r.json()["default"] is True
    r2 = await import_env.delete("/exits/myvpn")
    assert r2.status_code == 409
    assert "default route" in r2.json()["detail"]

async def test_delete_non_default_imported_exit_ok(import_env):
    await import_env.post("/exits/import", json={"id": "first", "conf_text": CONF})   # becomes default
    r = await import_env.post("/exits/import", json={"id": "second", "conf_text": CONF})
    assert r.json()["default"] is False
    r2 = await import_env.delete("/exits/second")
    assert r2.status_code == 200
