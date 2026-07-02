import pytest
from routepanel.settings import get_setting, set_setting, get_default_exit_id
from routepanel.config import Config

async def test_settings_roundtrip(tmp_db):
    assert await get_setting(tmp_db, "x") is None
    await set_setting(tmp_db, "x", "1")
    await set_setting(tmp_db, "x", "2")   # upsert
    await tmp_db.commit()
    assert await get_setting(tmp_db, "x") == "2"

async def test_default_exit_resolution(tmp_db):
    cfg = Config()
    assert await get_default_exit_id(tmp_db, cfg) == "direct"
    cfg2 = Config(default_exit_id="doprax")
    assert await get_default_exit_id(tmp_db, cfg2) == "doprax"
    await set_setting(tmp_db, "default_exit_id", "myexit")
    await tmp_db.commit()
    assert await get_default_exit_id(tmp_db, cfg2) == "myexit"
