# tests/api/test_exits.py
import pytest

@pytest.mark.asyncio
async def test_list_exits(test_client):
    r = await test_client.get("/exits")
    assert r.status_code == 200
    assert "doprax" in r.text

@pytest.mark.asyncio
async def test_add_exit(test_client):
    r = await test_client.post("/exits", json={
        "id": "hetzner2", "interface": "awg2", "fwmark": 101,
        "routing_table": "vpn2", "health_check_ip": "1.1.1.1",
        "fallback_exit_id": "direct", "priority": 2
    })
    assert r.status_code == 200
    r2 = await test_client.get("/exits")
    assert "hetzner2" in r2.text

@pytest.mark.asyncio
async def test_reject_exit_hijacking_main_table(test_client):
    # A non-direct exit (fwmark != 0) on the 'main' table would hijack the
    # host's default route and isolate the box -- the API must refuse it.
    r = await test_client.post("/exits", json={
        "id": "bad", "interface": "awg1", "fwmark": 199,
        "routing_table": "main", "health_check_ip": "1.1.1.1",
        "fallback_exit_id": "direct", "priority": 9
    })
    assert r.status_code == 422
    r2 = await test_client.get("/exits")
    assert "bad" not in r2.text

@pytest.mark.asyncio
async def test_delete_exit(test_client):
    r = await test_client.delete("/exits/doprax")
    assert r.status_code == 200
    r2 = await test_client.get("/exits")
    assert "doprax" not in r2.text

@pytest.mark.asyncio
async def test_delete_referenced_exit_rejected(test_client):
    await test_client.post("/domains", json={
        "name": "Y", "domains": ["y.com"], "exit_id": "doprax", "ospf_distribute": False
    })
    r = await test_client.delete("/exits/doprax")
    assert r.status_code == 409
