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


# --- warm start (2026-10-18): a routesyncd restart must not fail rules over ---
# Cold start used to begin every exit DOWN -> 12 doprax rules went to KZ/direct
# for ~7 min (3x30s up-hysteresis + 300s failback dwell from up_since) and
# awg-watchdog alerted "all foreign exits down" while the tunnels were fine.

async def _seed_exits(db):
    await db.execute("INSERT INTO exits(id,interface,fwmark,routing_table) VALUES (?,?,?,?)",
                     ("direct","eth0",0,"main"))
    await db.execute("INSERT INTO exits(id,interface,fwmark,routing_table,fallback_exit_id) VALUES (?,?,?,?,?)",
                     ("doprax","awg1",100,"vpn","direct"))
    await db.execute("INSERT INTO exits(id,interface,fwmark,routing_table,fallback_exit_id) VALUES (?,?,?,?,?)",
                     ("kz","awg5",102,"vpn3","direct"))

async def _health_row(db, exit_id, status, age_sec, latency=50.0):
    await db.execute(
        "INSERT INTO exit_health(exit_id,status,latency_ms,checked_at) VALUES(?,?,?,datetime('now',?))",
        (exit_id, status, latency, f"-{age_sec} seconds"))

@pytest.mark.asyncio
async def test_seed_health_takes_fresh_rows_without_dwell_clock(tmp_db):
    from routepanel.syncd.main import load_seed_health
    await _seed_exits(tmp_db)
    await _health_row(tmp_db, "doprax", "up", 10, 52.4)
    await _health_row(tmp_db, "kz", "down", 10)
    await tmp_db.commit()
    seed = await load_seed_health(tmp_db, max_age_sec=90)
    assert seed["doprax"].status == HealthStatus.UP
    assert seed["doprax"].latency_ms == 52.4
    assert seed["doprax"].up_since is None      # no failback-dwell clock for seeded state
    assert seed["kz"].status == HealthStatus.DOWN

@pytest.mark.asyncio
async def test_seed_health_ignores_stale_and_unknown_rows(tmp_db):
    from routepanel.syncd.main import load_seed_health
    await _seed_exits(tmp_db)
    await _health_row(tmp_db, "doprax", "up", 600)      # daemon was down for 10 min
    await _health_row(tmp_db, "kz", "unknown", 5)
    await tmp_db.commit()
    assert await load_seed_health(tmp_db, max_age_sec=90) == {}

@pytest.mark.asyncio
async def test_seeded_primary_keeps_rule_on_primary_after_restart(tmp_db):
    from routepanel.syncd.main import load_seed_health
    await _seed_exits(tmp_db)
    await _health_row(tmp_db, "doprax", "up", 10)
    await _health_row(tmp_db, "direct", "up", 10, 0.0)
    await tmp_db.commit()
    seed = await load_seed_health(tmp_db, max_age_sec=90)
    # fresh daemon: prev defaults to the rule's own exit, dwell configured
    assert await get_effective_exit(tmp_db, "doprax", None, seed, "doprax", 300) == "doprax"
