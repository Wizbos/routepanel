# tests/api/test_domains.py
import pytest, json

@pytest.mark.asyncio
async def test_add_and_list_domain_rule(test_client):
    r = await test_client.post("/domains", json={
        "name": "YouTube",
        "domains": ["youtube.com", "googlevideo.com"],
        "exit_id": "doprax",
        "ospf_distribute": True,
        "notes": "test"
    })
    assert r.status_code == 200
    r2 = await test_client.get("/")
    assert "YouTube" in r2.text

@pytest.mark.asyncio
async def test_delete_domain_rule(test_client):
    await test_client.post("/domains", json={
        "name": "Netflix", "domains": ["netflix.com"],
        "exit_id": "direct", "ospf_distribute": False
    })
    r_list = await test_client.get("/")
    assert "Netflix" in r_list.text
    await test_client.delete("/domains/1")
    r2 = await test_client.get("/")
    assert "Netflix" not in r2.text

@pytest.mark.asyncio
async def test_invalid_exit_rejected(test_client):
    r = await test_client.post("/domains", json={
        "name": "X", "domains": ["x.com"],
        "exit_id": "nonexistent", "ospf_distribute": False
    })
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_edit_domain_rule(test_client):
    await test_client.post("/domains", json={
        "name": "Old", "domains": ["old.com"], "exit_id": "doprax", "ospf_distribute": False
    })
    r = await test_client.put("/domains/1", json={
        "name": "New", "domains": ["new.com"], "exit_id": "direct", "ospf_distribute": True
    })
    assert r.status_code == 200
    r2 = await test_client.get("/")
    assert "New" in r2.text and "Old" not in r2.text

@pytest.mark.asyncio
async def test_list_returns_all_rules_ignoring_legacy_filter_params(test_client):
    await test_client.post("/domains", json={
        "name": "Alpha", "domains": ["alpha.com"], "exit_id": "doprax", "ospf_distribute": True})
    await test_client.post("/domains", json={
        "name": "Beta", "domains": ["beta.com"], "exit_id": "direct", "ospf_distribute": False})
    # Filtering is now client-side: legacy query params must NOT drop rows server-side.
    r = await test_client.get("/?q=zzz&exit_filter=doprax&ospf_only=1")
    assert r.status_code == 200
    assert "Alpha" in r.text and "Beta" in r.text

@pytest.mark.asyncio
async def test_rule_row_exposes_client_filter_dataset(test_client):
    await test_client.post("/domains", json={
        "name": "YouTube", "domains": ["youtube.com", "googlevideo.com"],
        "exit_id": "doprax", "ospf_distribute": True})
    r = await test_client.get("/")
    # table.js filters/sorts off these row attributes:
    assert 'data-exit="doprax"' in r.text
    assert 'data-ospf="1"' in r.text
    assert 'dot-unknown' in r.text            # exit_health reaches template; no health row -> "unknown" dot
    assert "googlevideo.com" in r.text        # secondary domain is searchable via data-search


# --- static_cidrs validation/normalization (regression: 2026-06-15 "pending" bug) ---

@pytest.mark.asyncio
async def test_static_cidr_bare_ip_normalized_to_32(test_client):
    # A bare host IP must be accepted and stored as /32 -- FRR's `vtysh ip route`
    # rejects a maskless IP, which previously aborted the whole sync.
    r = await test_client.post("/domains", json={
        "name": "Bare", "domains": ["bare.com"], "exit_id": "doprax",
        "ospf_distribute": True, "static_cidrs": ["172.67.72.55", "8.6.112.0/24"]})
    assert r.status_code == 200
    page = await test_client.get("/")
    assert "172.67.72.55/32" in page.text
    assert "8.6.112.0/24" in page.text

@pytest.mark.asyncio
async def test_static_cidr_garbage_rejected_422(test_client):
    r = await test_client.post("/domains", json={
        "name": "Junk", "domains": ["junk.com"], "exit_id": "doprax",
        "ospf_distribute": True, "static_cidrs": ["not-an-ip"]})
    assert r.status_code == 422
    page = await test_client.get("/")
    assert "Junk" not in page.text

@pytest.mark.asyncio
async def test_put_static_cidr_normalized(test_client):
    await test_client.post("/domains", json={
        "name": "Edit", "domains": ["edit.com"], "exit_id": "doprax", "ospf_distribute": False})
    r = await test_client.put("/domains/1", json={
        "name": "Edit", "domains": ["edit.com"], "exit_id": "doprax",
        "ospf_distribute": True, "static_cidrs": ["104.26.15.17"]})
    assert r.status_code == 200
    page = await test_client.get("/")
    assert "104.26.15.17/32" in page.text

@pytest.mark.asyncio
async def test_put_static_cidr_garbage_rejected_422(test_client):
    await test_client.post("/domains", json={
        "name": "Edit2", "domains": ["edit2.com"], "exit_id": "doprax", "ospf_distribute": False})
    r = await test_client.put("/domains/1", json={
        "name": "Edit2", "domains": ["edit2.com"], "exit_id": "doprax",
        "ospf_distribute": True, "static_cidrs": ["999.1.1.1"]})
    assert r.status_code == 422
