import json, pytest
from unittest.mock import patch

@pytest.fixture
async def awg_client(test_client, tmp_path):
    # seed AWG server identity + point conf path into tmp
    from routepanel import config as cfg_mod
    from routepanel.db import open_db
    from routepanel.settings import set_setting
    cfg_mod._config.awg_conf_path = str(tmp_path / "awg0.conf")
    db = await open_db()
    for k, v in [("awg.private_key","SPRIV="),("awg.public_key","SPUB="),
                 ("awg.subnet","10.8.0.0/24"),("awg.port","51820"),
                 ("awg.endpoint","203.0.113.5:51820"),("awg.params","{}")]:
        await set_setting(db, k, v)
    await db.commit(); await db.close()
    return test_client

async def test_create_client(awg_client):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=","CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        r = await awg_client.post("/clients", json={"name": "phone"})
    assert r.status_code == 200
    assert r.json()["address"] == "10.8.0.2"

async def test_create_without_server_503(test_client):
    r = await test_client.post("/clients", json={"name": "phone"})
    assert r.status_code == 503

async def test_conf_and_qr(awg_client):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=","CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        cid = (await awg_client.post("/clients", json={"name": "phone"})).json()["id"]
    conf = await awg_client.get(f"/clients/{cid}/conf")
    assert conf.status_code == 200
    assert "PrivateKey = CPRIV=" in conf.text
    assert "DNS = 10.8.0.1" in conf.text
    qr = await awg_client.get(f"/clients/{cid}/qr")
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/svg")

async def test_revoke_is_soft(awg_client):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=","CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        cid = (await awg_client.post("/clients", json={"name": "old"})).json()["id"]
        r = await awg_client.post(f"/clients/{cid}/revoke")
    assert r.status_code == 200
    assert (await awg_client.get(f"/clients/{cid}/conf")).status_code == 404
    # row survives (soft delete)
    from routepanel.db import open_db
    db = await open_db()
    async with db.execute("SELECT enabled, revoked_at FROM clients WHERE id=?", (cid,)) as cur:
        row = await cur.fetchone()
    await db.close()
    assert row["enabled"] == 0 and row["revoked_at"] is not None

async def test_duplicate_name_422(awg_client):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=","CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        await awg_client.post("/clients", json={"name": "dup"})
        r = await awg_client.post("/clients", json={"name": "dup"})
    assert r.status_code == 422

async def test_bad_name_rejected(awg_client):
    r = await awg_client.post("/clients", json={"name": 'my"dev\r\nice'})
    assert r.status_code == 422

async def test_revoked_name_can_be_reused(awg_client):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=","CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        cid = (await awg_client.post("/clients", json={"name": "phone"})).json()["id"]
        await awg_client.post(f"/clients/{cid}/revoke")
        r = await awg_client.post("/clients", json={"name": "phone"})   # reuse after revoke
    assert r.status_code == 200

async def test_conf_and_qr_no_store(awg_client):
    with patch("routepanel.awgserver.gen_keypair", return_value=("CPRIV=","CPUB=")), \
         patch("routepanel.awgserver.gen_psk", return_value="PSK="), \
         patch("subprocess.run"):
        cid = (await awg_client.post("/clients", json={"name": "cacheck"})).json()["id"]
    conf = await awg_client.get(f"/clients/{cid}/conf")
    qr = await awg_client.get(f"/clients/{cid}/qr")
    assert conf.headers["cache-control"] == "no-store"
    assert qr.headers["cache-control"] == "no-store"
