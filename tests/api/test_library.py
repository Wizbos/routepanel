# tests/api/test_library.py
import pytest

@pytest.mark.asyncio
async def test_add_and_list_pack(test_client):
    r = await test_client.post("/library", json={
        "id": "youtube", "name": "YouTube",
        "domains": ["youtube.com", "googlevideo.com"]
    })
    assert r.status_code == 200
    r2 = await test_client.get("/library")
    assert "YouTube" in r2.text

@pytest.mark.asyncio
async def test_update_pack(test_client):
    await test_client.post("/library", json={
        "id": "spotify", "name": "Spotify", "domains": ["spotify.com"]
    })
    r = await test_client.put("/library/spotify", json={
        "name": "Spotify", "domains": ["spotify.com", "scdn.co"]
    })
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_patch_pack_cidrs(test_client):
    await test_client.post("/library", json={
        "id": "google", "name": "Google", "domains": ["google.com"]
    })
    r = await test_client.patch("/library/google/cidrs", json={"cidrs": ["142.250.0.0/15"]})
    assert r.status_code == 200
    r2 = await test_client.get("/library")
    assert "142.250.0.0/15" in r2.text

@pytest.mark.asyncio
async def test_delete_pack(test_client):
    await test_client.post("/library", json={
        "id": "tmp", "name": "Tmp", "domains": ["tmp.com"]
    })
    r = await test_client.delete("/library/tmp")
    assert r.status_code == 200
    r2 = await test_client.get("/library")
    assert "Tmp" not in r2.text


# --- pack cidrs validation/normalization (regression: 2026-06-15 "pending" bug) ---

@pytest.mark.asyncio
async def test_pack_bare_ip_cidr_normalized(test_client):
    r = await test_client.post("/library", json={
        "id": "hiveos", "name": "HiveOS", "domains": ["hiveos.farm"],
        "cidrs": ["172.67.72.55", "8.6.112.0/24"]})
    assert r.status_code == 200
    page = await test_client.get("/library")
    assert "172.67.72.55/32" in page.text

@pytest.mark.asyncio
async def test_pack_garbage_cidr_rejected_422(test_client):
    r = await test_client.post("/library", json={
        "id": "bad", "name": "BadPack", "domains": ["bad.com"], "cidrs": ["nope"]})
    assert r.status_code == 422
    page = await test_client.get("/library")
    assert "BadPack" not in page.text

@pytest.mark.asyncio
async def test_pack_patch_cidrs_normalized(test_client):
    await test_client.post("/library", json={"id": "g", "name": "G", "domains": ["g.com"]})
    r = await test_client.patch("/library/g/cidrs", json={"cidrs": ["104.26.14.17"]})
    assert r.status_code == 200
    page = await test_client.get("/library")
    assert "104.26.14.17/32" in page.text

@pytest.mark.asyncio
async def test_pack_patch_garbage_rejected_422(test_client):
    await test_client.post("/library", json={"id": "g2", "name": "G2", "domains": ["g2.com"]})
    r = await test_client.patch("/library/g2/cidrs", json={"cidrs": ["1.2.3.4/33"]})
    assert r.status_code == 422
