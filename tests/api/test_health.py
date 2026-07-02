async def test_health_shape(test_client):
    r = await test_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert {e["id"] for e in body["exits"]} == {"doprax", "direct"}
    assert isinstance(body["syncd_alive"], bool)

async def test_health_bypasses_auth(test_client, tmp_path):
    from routepanel import config as cfg_mod
    from routepanel.panel import auth
    pw = tmp_path / "p"; pw.write_text(auth.hash_password("x"))
    cfg_mod._config.password_file = str(pw)
    try:
        assert (await test_client.get("/health")).status_code == 200
    finally:
        cfg_mod._config.password_file = "/nonexistent"
