# src/routepanel/syncd/main.py
import asyncio, json, os, signal, logging, time
import aiosqlite
from routepanel.config import get_config
from routepanel.db import open_db
from routepanel.syncd.resolver import resolve_domains
from routepanel.syncd.health import check_exit, ExitHealth, HealthStatus
from routepanel.syncd import ipset_manager, frr_manager, routing_manager, dnsmasq_manager
from routepanel.syncd.ospf import build_ospf_desired

log = logging.getLogger("routesyncd")
_health: dict[str, ExitHealth] = {}
_sync_lock = asyncio.Lock()           # serialises periodic + SIGUSR1 syncs
_last_effective: dict[int, str] = {}  # rule_id -> last effective exit (transition + dwell)
_last_default: str | None = None      # last effective default exit (transition + dwell)
_last_ospf_pushed: set[str] = set()   # last set of prefixes pushed to FRR
_last_frr_sync: float = 0.0           # monotonic ts of last FRR push (debounce)

def _usable(h: ExitHealth | None) -> bool:
    return h is None or h.status != HealthStatus.DOWN

async def get_effective_exit(db: aiosqlite.Connection, primary_exit_id: str,
                             fallback_override_id: str | None,
                             health: dict[str, ExitHealth],
                             prev: str | None = None, dwell: int = 0) -> str:
    """Walk the fallback chain to the first usable exit. **Failback dwell**: if
    we're currently on `prev` (a still-usable fallback) and a higher exit in the
    chain only recovered < `dwell` seconds ago, stay on `prev` -- so a primary
    flapping every couple of minutes can't bounce traffic. With prev/dwell unset
    this is a plain status walk."""
    start = fallback_override_id or primary_exit_id
    visited: set[str] = set()
    current = start
    while current and current not in visited:
        visited.add(current)
        h = health.get(current)
        if _usable(h):
            if (prev and current != prev and dwell and h is not None
                    and h.up_since is not None
                    and (time.monotonic() - h.up_since) < dwell
                    and _usable(health.get(prev))):
                return prev          # higher exit recovered too recently -- hold on the fallback
            return current
        async with db.execute("SELECT fallback_exit_id FROM exits WHERE id=?", (current,)) as cur:
            row = await cur.fetchone()
        if not row or not row["fallback_exit_id"]:
            return current
        current = row["fallback_exit_id"]
    return start

def _maybe_push_frr(desired: set[str], cfg) -> None:
    """Debounced + batched OSPF push (§8.1). Only pushes when the set changed
    AND at least ospf_debounce_sec elapsed since the last push, so short-TTL CDN
    churn can't flood LSAs. A skipped change is flushed on a later cycle."""
    global _last_ospf_pushed, _last_frr_sync
    if desired == _last_ospf_pushed:
        return
    now = time.monotonic()
    if now - _last_frr_sync < cfg.ospf_debounce_sec:
        return
    try:
        added, removed = frr_manager.sync_routes_batch(desired, cfg.frr_next_hop)
    except Exception as e:
        # A failed OSPF push must never abort the sync cycle: the DB commit
        # (resolved_ips/history) runs after this, and letting the exception
        # propagate rolls it back -- freezing every rule's state (the
        # 2026-06-15 'pending' bug). Log and retry next cycle.
        log.error("FRR push failed (continuing; OSPF may lag a cycle): %s", e)
        return
    _last_ospf_pushed = set(desired)
    _last_frr_sync = now
    if added or removed:
        log.info("FRR: +%d -%d routes", len(added), len(removed))

async def run_sync() -> None:
    """Public entry -- lock guarantees the periodic loop and a SIGUSR1-triggered
    run never overlap (no ipset/FRR thrash, no concurrent SQLite writers)."""
    async with _sync_lock:
        await _run_sync_inner()

async def _run_sync_inner() -> None:
    global _last_default
    cfg = get_config()
    # autocommit: this cycle interleaves DB writes with multi-second DNS/ipset/
    # FRR/dnsmasq work. Holding one write transaction across all of it locks out
    # concurrent panel saves ("database is locked"). Per-statement commits keep
    # the WAL write lock held only momentarily. See open_db(autocommit=...).
    db = await open_db(autocommit=True)
    try:
        async with db.execute(
            "SELECT id, name, domains, exit_id, fallback_override_id, ospf_distribute, static_cidrs FROM domain_rules"
        ) as cur:
            rules = [dict(r) for r in await cur.fetchall()]
        async with db.execute("SELECT * FROM exits") as cur:
            exits = [dict(r) for r in await cur.fetchall()]
        fwmark_of = {e["id"]: e["fwmark"] for e in exits}

        effective_fwmark: dict[int, int] = {}   # rule_id -> fwmark for the chain
        ospf_desired: set[str] = set()           # full prefixes (static CIDRs + /32 live)

        # Default catch-all is failover-aware too (default_exit_id + fallback chain).
        default_eff = await get_effective_exit(
            db, cfg.default_exit_id, None, _health, _last_default, cfg.failback_min_dwell_sec
        )
        baseline = _last_default or cfg.default_exit_id
        if default_eff != baseline:
            action = "failback" if default_eff == cfg.default_exit_id else "failover"
            await db.execute("INSERT INTO history(action,exit_id,detail) VALUES(?,?,?)",
                             (action, default_eff, f"default {baseline} -> {default_eff}"))
        _last_default = default_eff
        default_fwmark = fwmark_of.get(default_eff, 0)

        for rule in rules:
            resolved = await resolve_domains(
                json.loads(rule["domains"]), cfg.resolver_address, cfg.resolver_port
            )
            static = set(json.loads(rule.get("static_cidrs") or "[]"))

            prev = _last_effective.get(rule["id"], rule["exit_id"])
            effective = await get_effective_exit(
                db, rule["exit_id"], rule["fallback_override_id"], _health,
                prev, cfg.failback_min_dwell_sec
            )
            effective_fwmark[rule["id"]] = fwmark_of.get(effective, 0)

            if effective != prev:   # transition only -- no per-cycle spam, no IP moving
                action = "failback" if effective == rule["exit_id"] else "failover"
                await db.execute(
                    "INSERT INTO history(action,domain_rule_id,exit_id,detail) VALUES(?,?,?,?)",
                    (action, rule["id"], effective, f"{prev} -> {effective}")
                )
            _last_effective[rule["id"]] = effective

            # rule_<id> set = static CIDRs (always) + best-effort resolved IPs.
            # Add-only; dnsmasq-added live IPs are preserved, stale ones time out.
            ipset_manager.refresh_members_batch(rule["id"], static | resolved, cfg.ipset_timeout_sec)

            # OSPF: built from the LIVE ipset membership (static CIDRs verbatim +
            #       resolved /32s clients actually got via dnsmasq) -- not just this
            #       cycle's daemon lookup, so corp routing covers exactly the IPs in
            #       use (kills anycast drift). /32s capped (LSA-storm guard).
            if rule["ospf_distribute"]:
                members = ipset_manager.get_members(rule["id"])
                rule_prefixes = build_ospf_desired(
                    members, json.loads(rule.get("static_cidrs") or "[]"), cfg.max_ospf_ips_per_rule
                )
                host_count = sum(1 for m in members if "/" not in m)
                if host_count > cfg.max_ospf_ips_per_rule:
                    await db.execute(
                        "INSERT INTO history(action,domain_rule_id,exit_id,detail) VALUES(?,?,?,?)",
                        ("sync", rule["id"], effective,
                         f"OSPF cap: {cfg.max_ospf_ips_per_rule}/{host_count} live IPs for {rule['name']}")
                    )
                ospf_desired |= rule_prefixes

            for ip in resolved:
                await db.execute("""
                    INSERT INTO resolved_ips(domain_rule_id, ip) VALUES(?,?)
                    ON CONFLICT(domain_rule_id, ip) DO UPDATE SET last_seen=datetime('now')
                """, (rule["id"], ip))

        # Reap ipsets for deleted rules (the chain already stopped matching them).
        live_ids = {r["id"] for r in rules}
        for gone in [rid for rid in list(_last_effective) if rid not in live_ids]:
            routing_manager.remove_wan_nat(gone, cfg.wan_interface)
            ipset_manager.destroy_ipset(gone)
            _last_effective.pop(gone, None)

        # Reconcile routing every cycle: per-rule chain (failover = rebuild) +
        # ip rules + tables, so panel-added exits/rules apply without a reboot.
        try:
            routing_manager.reconcile(exits, rules, effective_fwmark, default_fwmark)
        except Exception as e:
            log.error("routing reconcile failed: %s", e)

        # dnsmasq fragment: only changes when a rule's domains change (rule_<id> is
        # exit-independent), so this is a near-no-op except on edits.
        if cfg.dns_intercept:
            try:
                dnsmasq_manager.sync_fragment(cfg.dnsmasq_conf_path, cfg.dnsmasq_service, rules)
            except Exception as e:
                log.error("dnsmasq sync failed: %s", e)

        _maybe_push_frr(ospf_desired, cfg)
        ipset_manager.save_all(cfg.ipsets_save_path)

        await db.execute("DELETE FROM resolved_ips WHERE last_seen < datetime('now', ?)",
                         (f"-{cfg.resolved_ip_ttl_days} days",))
        await db.commit()
        log.info("sync complete")
    except Exception as e:
        log.error("sync error: %s", e)
    finally:
        await db.close()

async def _health_loop(cfg) -> None:
    while True:
        db = await open_db()
        try:
            async with db.execute("SELECT id, interface, fwmark, health_check_ip FROM exits") as cur:
                exits = await cur.fetchall()
        finally:
            await db.close()
        for row in exits:
            eid = row["id"]
            if eid not in _health:
                _health[eid] = ExitHealth(exit_id=eid)
            _health[eid] = await check_exit(
                eid, row["interface"], row["fwmark"], row["health_check_ip"],
                _health[eid], cfg.health_latency_threshold_ms,
                cfg.health_down_threshold, cfg.health_up_threshold
            )
        # Persist health so the panel (separate process) can see it -- the
        # in-memory _health dict is private to this daemon's process.
        db = await open_db()
        try:
            for row in exits:
                h = _health[row["id"]]
                await db.execute(
                    "INSERT INTO exit_health(exit_id,status,latency_ms,checked_at) "
                    "VALUES(?,?,?,datetime('now')) "
                    "ON CONFLICT(exit_id) DO UPDATE SET status=excluded.status, "
                    "latency_ms=excluded.latency_ms, checked_at=excluded.checked_at",
                    (row["id"], h.status.value, h.latency_ms),
                )
            await db.commit()
        finally:
            await db.close()
        await asyncio.sleep(cfg.health_interval)

async def _sync_loop(cfg) -> None:
    while True:
        await run_sync()
        await asyncio.sleep(cfg.poll_interval)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = get_config()

    # Write PID file so routepanel can send SIGUSR1 to trigger immediate sync
    pid_file = "/run/routesyncd.pid"
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # create_task (not ensure_future) on the explicit loop; run_sync's lock makes
    # the triggered run safe even if a periodic sync is in flight.
    loop.add_signal_handler(signal.SIGUSR1, lambda: loop.create_task(run_sync()))
    try:
        loop.run_until_complete(asyncio.gather(_health_loop(cfg), _sync_loop(cfg)))
    finally:
        loop.close()
        try:
            os.unlink(pid_file)
        except FileNotFoundError:
            pass
