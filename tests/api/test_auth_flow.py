import pytest
from httpx import AsyncClient, ASGITransport
from routepanel.panel import auth

@pytest.fixture
async def auth_client(tmp_path, test_client):
    # test_client fixture already built the app/db; add a password file to the live config
    from routepanel import config as cfg_mod
    pw_file = tmp_path / "panel.passwd"
    pw_file.write_text(auth.hash_password("pw123") + "\n")
    cfg_mod._config.password_file = str(pw_file)
    yield test_client
    cfg_mod._config.password_file = "/nonexistent"

async def test_unauthenticated_html_redirects(auth_client):
    r = await auth_client.get("/exits", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"

async def test_unauthenticated_api_gets_401(auth_client):
    r = await auth_client.get("/exits", follow_redirects=False)
    assert r.status_code == 401

async def test_login_and_access(auth_client):
    r = await auth_client.post("/login", data={"password": "pw123"}, follow_redirects=False)
    assert r.status_code == 303
    assert "rp_session" in r.cookies
    auth_client.cookies.update(r.cookies)
    assert (await auth_client.get("/exits")).status_code == 200

async def test_wrong_password(auth_client):
    r = await auth_client.post("/login", data={"password": "nope"})
    assert r.status_code == 401

async def test_no_password_file_means_open(test_client):
    assert (await test_client.get("/exits")).status_code == 200
