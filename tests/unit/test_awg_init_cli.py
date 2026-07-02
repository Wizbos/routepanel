# tests/unit/test_awg_init_cli.py
"""routepanel-awg-init: empty --awg-params must be filled with real
AmneziaWG obfuscation params (Fix 7) rather than shipping vanilla WireGuard."""
import json
from unittest.mock import patch

from routepanel import awg_init_cli
from routepanel.db import open_db
from routepanel.settings import get_setting


def _args(**overrides):
    a = type("Args", (), {})()
    a.endpoint = "203.0.113.5:51820"
    a.subnet = "10.8.0.0/24"
    a.port = 51820
    a.awg_params = "{}"
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


async def test_awg_init_generates_params_when_empty(tmp_db, tmp_path):
    from routepanel import config as cfg_mod

    cfg_mod.reset_config()
    cfg_mod._config = cfg_mod.Config(awg_conf_path=str(tmp_path / "awg0.conf"))
    db_path = str(tmp_path / "test.db")

    async def _fake_open_db(*a, **kw):
        return tmp_db

    with patch.object(awg_init_cli, "open_db", _fake_open_db), \
         patch("routepanel.awgserver.gen_keypair", return_value=("SPRIV=", "SPUB=")), \
         patch("subprocess.run"):
        await awg_init_cli._run(_args())

    # _run() closes the connection it opened; reopen the same file to read back.
    db2 = await open_db(db_path)
    stored = json.loads(await get_setting(db2, "awg.params"))
    await db2.close()

    assert stored  # non-empty: real params were generated, not left as {}
    for k in ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"):
        assert k in stored

    cfg_mod.reset_config()
