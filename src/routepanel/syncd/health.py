# src/routepanel/syncd/health.py
import asyncio, time
from dataclasses import dataclass
from enum import Enum

class HealthStatus(str, Enum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"

@dataclass
class ExitHealth:
    exit_id: str
    status: HealthStatus = HealthStatus.DOWN
    latency_ms: float | None = None
    fail_count: int = 0
    success_count: int = 0          # consecutive successes while DOWN (recovery hysteresis)
    up_since: float | None = None   # monotonic ts the exit became usable (for failback dwell)

import re
_PING_TIME = re.compile(r"time[=<]([\d.]+)\s*ms")

async def ping_via_interface(ip: str, interface: str, timeout: float = 2.0) -> float | None:
    proc = await asyncio.create_subprocess_exec(
        "ping", "-c", "1", "-W", str(int(timeout)), "-I", interface, ip,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 1)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    if proc.returncode != 0:
        return None
    # Parse the RTT ping itself reports, not wall-clock (which includes fork/exec).
    m = _PING_TIME.search(out.decode(errors="ignore"))
    return float(m.group(1)) if m else 0.0

async def check_exit(exit_id: str, interface: str, fwmark: int, target_ip: str,
                     health: ExitHealth, threshold_ms: float,
                     down_threshold: int, up_threshold: int = 3) -> ExitHealth:
    # An exit with no fwmark is the direct path -- always considered up.
    if fwmark == 0:
        return ExitHealth(exit_id=exit_id, status=HealthStatus.UP, latency_ms=0.0,
                          up_since=health.up_since or time.monotonic())
    latency = await ping_via_interface(target_ip, interface)
    if latency is None:
        health.fail_count += 1
        health.success_count = 0
        health.latency_ms = None
        if health.fail_count >= down_threshold and health.status != HealthStatus.DOWN:
            health.status = HealthStatus.DOWN
            health.up_since = None
    else:
        health.fail_count = 0
        health.latency_ms = latency
        new_status = HealthStatus.DEGRADED if latency >= threshold_ms else HealthStatus.UP
        if health.status == HealthStatus.DOWN:
            # Recovery hysteresis: require up_threshold consecutive successes,
            # not one lucky ping, before declaring the exit usable again.
            health.success_count += 1
            if health.success_count >= up_threshold:
                health.status = new_status
                health.success_count = 0
                health.up_since = time.monotonic()   # starts the failback dwell clock
        else:
            health.status = new_status
            if health.up_since is None:
                health.up_since = time.monotonic()
    return health
