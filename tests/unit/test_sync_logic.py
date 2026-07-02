# tests/unit/test_sync_logic.py
import pytest, json
from routepanel.syncd.main import get_effective_exit
from routepanel.syncd.health import ExitHealth, HealthStatus

def make_health(exit_id: str, status: HealthStatus) -> ExitHealth:
    return ExitHealth(exit_id=exit_id, status=status)

@pytest.mark.asyncio
async def test_effective_exit_primary_up(tmp_db):
    # direct must exist before doprax references it as fallback (FK enforced).
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES (?,?,?,?)",
                         ("direct","eth0",0,"main"))
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table,fallback_exit_id) VALUES (?,?,?,?,?)",
                         ("doprax","awg1",100,"vpn","direct"))
    await tmp_db.commit()
    health = {"doprax": make_health("doprax", HealthStatus.UP)}
    result = await get_effective_exit(tmp_db, "doprax", None, health)
    assert result == "doprax"

@pytest.mark.asyncio
async def test_effective_exit_failover_to_fallback(tmp_db):
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES (?,?,?,?)",
                         ("direct","eth0",0,"main"))
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table,fallback_exit_id) VALUES (?,?,?,?,?)",
                         ("doprax","awg1",100,"vpn","direct"))
    await tmp_db.commit()
    health = {
        "doprax": make_health("doprax", HealthStatus.DOWN),
        "direct": make_health("direct", HealthStatus.UP),
    }
    result = await get_effective_exit(tmp_db, "doprax", None, health)
    assert result == "direct"

@pytest.mark.asyncio
async def test_effective_exit_override_used(tmp_db):
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES (?,?,?,?)",
                         ("direct","eth0",0,"main"))
    await tmp_db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES (?,?,?,?)",
                         ("doprax","awg1",100,"vpn"))
    await tmp_db.commit()
    health = {"direct": make_health("direct", HealthStatus.UP)}
    result = await get_effective_exit(tmp_db, "doprax", "direct", health)
    assert result == "direct"
