import os, sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import mkclient  # noqa: E402  (path tweak above must run first)


@pytest.fixture
async def awg_client_env(tmp_path, monkeypatch):
    """Point routepanel's config at a scratch DB with an AWG server already
    provisioned, the same shape as tests/api's awg_client fixture."""
    from routepanel import config as cfg_mod
    from routepanel.db import open_db
    from routepanel.settings import set_setting

    monkeypatch.setenv("ROUTEPANEL_CONFIG", "")
    cfg_mod.reset_config()
    db_path = str(tmp_path / "test.db")
    cfg_mod._config = cfg_mod.Config(
        db_path=db_path, awg_conf_path=str(tmp_path / "awg0.conf")
    )

    db = await open_db(db_path)
    for k, v in [
        ("awg.private_key", "SPRIV="),
        ("awg.public_key", "SPUB="),
        ("awg.subnet", "10.8.0.0/24"),
        ("awg.port", "51820"),
        ("awg.endpoint", "203.0.113.5:51820"),
        ("awg.params", "{}"),
    ]:
        await set_setting(db, k, v)
    await db.commit()
    await db.close()
    yield
    cfg_mod.reset_config()


async def test_create_client(awg_client_env):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=", "CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        cid = await mkclient.create_client("phone")

    from routepanel.db import open_db
    db = await open_db()
    async with db.execute("SELECT * FROM clients WHERE id=?", (cid,)) as c:
        row = dict(await c.fetchone())
    await db.close()

    assert row["name"] == "phone"
    assert row["address"] == "10.8.0.2"
    assert row["public_key"] == "CPUB="


async def test_print_client_outputs_conf(awg_client_env, capsys):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=", "CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        cid = await mkclient.create_client("laptop")
        await mkclient.print_client(cid)

    out = capsys.readouterr().out
    assert "PrivateKey = CPRIV=" in out
    assert "client config" in out
