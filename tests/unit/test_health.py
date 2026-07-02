# tests/unit/test_health.py
import pytest
from routepanel.syncd.health import check_exit, ExitHealth, HealthStatus

@pytest.mark.asyncio
async def test_direct_always_up():
    # Directness is keyed on fwmark==0, never on the interface name.
    health = ExitHealth(exit_id="direct")
    result = await check_exit("direct", "eth0", 0, "1.1.1.1", health, 200.0, 3)
    assert result.status == HealthStatus.UP

@pytest.mark.asyncio
async def test_ping_success_keeps_up():
    from unittest.mock import patch, AsyncMock
    health = ExitHealth(exit_id="doprax", status=HealthStatus.UP)
    with patch("routepanel.syncd.health.ping_via_interface", new_callable=AsyncMock, return_value=15.0):
        result = await check_exit("doprax", "awg1", 100, "1.1.1.1", health, 200.0, 3, 3)
    assert result.status == HealthStatus.UP
    assert result.latency_ms == 15.0

@pytest.mark.asyncio
async def test_ping_fail_marks_down():
    from unittest.mock import patch, AsyncMock
    health = ExitHealth(exit_id="doprax", status=HealthStatus.UP, fail_count=2)
    with patch("routepanel.syncd.health.ping_via_interface", new_callable=AsyncMock, return_value=None):
        result = await check_exit("doprax", "awg1", 100, "1.1.1.1", health, 200.0, 3, 3)
    assert result.status == HealthStatus.DOWN
    assert result.fail_count == 3

@pytest.mark.asyncio
async def test_recovery_needs_consecutive_successes():
    # A DOWN exit must not flip UP on one lucky ping -- anti-flap hysteresis.
    from unittest.mock import patch, AsyncMock
    health = ExitHealth(exit_id="doprax", status=HealthStatus.DOWN)
    with patch("routepanel.syncd.health.ping_via_interface", new_callable=AsyncMock, return_value=10.0):
        r1 = await check_exit("doprax", "awg1", 100, "1.1.1.1", health, 200.0, 3, 3)
        assert r1.status == HealthStatus.DOWN          # 1 success -- not enough
        r2 = await check_exit("doprax", "awg1", 100, "1.1.1.1", r1, 200.0, 3, 3)
        assert r2.status == HealthStatus.DOWN          # 2 successes
        r3 = await check_exit("doprax", "awg1", 100, "1.1.1.1", r2, 200.0, 3, 3)
        assert r3.status == HealthStatus.UP            # 3rd -> recovered
