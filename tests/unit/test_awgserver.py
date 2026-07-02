import json, pytest
from unittest.mock import patch, MagicMock
from routepanel import awgserver
from routepanel.settings import set_setting

def test_gen_keypair_uses_awg_binary():
    with patch("shutil.which", side_effect=lambda b: "/usr/bin/awg" if b == "awg" else None), \
         patch("subprocess.run") as run:
        run.side_effect = [
            MagicMock(returncode=0, stdout="PRIV=\n"),
            MagicMock(returncode=0, stdout="PUB=\n"),
        ]
        priv, pub = awgserver.gen_keypair()
    assert (priv, pub) == ("PRIV=", "PUB=")
    assert run.call_args_list[0].args[0] == ["/usr/bin/awg", "genkey"]

def test_gen_awg_params_shape():
    p = awgserver.gen_awg_params()
    # required AmneziaWG obfuscation keys, all present as strings
    for k in ("Jc","Jmin","Jmax","S1","S2","H1","H2","H3","H4"):
        assert k in p and isinstance(p[k], str) and p[k].isdigit()
    jc, jmin, jmax = int(p["Jc"]), int(p["Jmin"]), int(p["Jmax"])
    assert 1 <= jc <= 10
    assert jmin < jmax
    # H1..H4 must be distinct (AWG requires it)
    assert len({p["H1"],p["H2"],p["H3"],p["H4"]}) == 4

def test_allocate_client_ip():
    assert awgserver.allocate_client_ip(set(), "10.8.0.0/24") == "10.8.0.2"
    assert awgserver.allocate_client_ip({"10.8.0.2"}, "10.8.0.0/24") == "10.8.0.3"

def test_allocate_skips_server_ip_in_odd_subnet():
    # /25 not on a .0 boundary: server (first host) is 10.8.0.129, so the
    # first client IP must be 10.8.0.130 -- no literal ".1" involved.
    assert awgserver.allocate_client_ip(set(), "10.8.0.128/25") == "10.8.0.130"

def test_allocate_exhausted():
    taken = {f"10.8.0.{i}" for i in range(2, 255)}
    with pytest.raises(RuntimeError):
        awgserver.allocate_client_ip(taken, "10.8.0.0/24")

def _server():
    return {"private_key": "SPRIV=", "public_key": "SPUB=", "subnet": "10.8.0.0/24",
            "port": 51820, "endpoint": "203.0.113.5:51820", "params": {"Jc": "4", "Jmin": "40"}}

def _client():
    return {"name": "phone", "private_key": "CPRIV=", "public_key": "CPUB=",
            "psk": "PSK=", "address": "10.8.0.2", "enabled": 1}

def test_render_server_conf():
    out = awgserver.render_server_conf(_server(), [_client()])
    assert "PrivateKey = SPRIV=" in out
    assert "Address = 10.8.0.1/24" in out
    assert "ListenPort = 51820" in out
    assert "Jc = 4" in out
    assert "[Peer]" in out and "PublicKey = CPUB=" in out
    assert "AllowedIPs = 10.8.0.2/32" in out

def test_render_server_conf_skips_revoked():
    c = _client(); c["enabled"] = 0
    assert "[Peer]" not in awgserver.render_server_conf(_server(), [c])

def test_render_client_conf():
    out = awgserver.render_client_conf(_server(), _client())
    assert "PrivateKey = CPRIV=" in out
    assert "Address = 10.8.0.2/32" in out
    assert "DNS = 10.8.0.1" in out                    # resolution=marking: clients use the VPS dnsmasq
    assert "Endpoint = 203.0.113.5:51820" in out
    assert "AllowedIPs = 0.0.0.0/0" in out
    assert "PersistentKeepalive = 25" in out
    assert "Jc = 4" in out

async def test_get_server_roundtrip(tmp_db):
    assert await awgserver.get_server(tmp_db) is None
    for k, v in [("awg.private_key","SPRIV="),("awg.public_key","SPUB="),
                 ("awg.subnet","10.8.0.0/24"),("awg.port","51820"),
                 ("awg.endpoint","1.2.3.4:51820"),("awg.params", json.dumps({"Jc":"4"}))]:
        await set_setting(tmp_db, k, v)
    await tmp_db.commit()
    srv = await awgserver.get_server(tmp_db)
    assert srv["port"] == 51820 and srv["params"] == {"Jc": "4"}

async def test_apply_server_conf_backs_up(tmp_db, tmp_path):
    from routepanel.config import Config
    cfg = Config(awg_conf_path=str(tmp_path / "awg0.conf"), awg_interface="awg0")
    for k, v in [("awg.private_key","SPRIV="),("awg.public_key","SPUB="),
                 ("awg.subnet","10.8.0.0/24"),("awg.port","51820"),
                 ("awg.endpoint","1.2.3.4:51820"),("awg.params","{}")]:
        await set_setting(tmp_db, k, v)
    await tmp_db.commit()
    (tmp_path / "awg0.conf").write_text("OLD")
    with patch("subprocess.run", return_value=MagicMock(returncode=0)) as run:
        await awgserver.apply_server_conf(tmp_db, cfg)
    assert (tmp_path / "awg0.conf.bak").read_text() == "OLD"   # backup before change
    assert "PrivateKey = SPRIV=" in (tmp_path / "awg0.conf").read_text()
