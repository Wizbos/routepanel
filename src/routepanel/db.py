# src/routepanel/db.py
import aiosqlite
from routepanel.config import get_config

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS exits (
    id TEXT PRIMARY KEY,
    interface TEXT NOT NULL,
    fwmark INTEGER NOT NULL DEFAULT 0,
    routing_table TEXT NOT NULL DEFAULT 'main',
    health_check_ip TEXT NOT NULL DEFAULT '1.1.1.1',
    fallback_exit_id TEXT REFERENCES exits(id),
    priority INTEGER NOT NULL DEFAULT 0,
    type TEXT NOT NULL DEFAULT 'manual'
);

-- Runtime health, written by routesyncd's health loop so the panel
-- (a separate process) can display it. NOT config -- safe to be lossy.
CREATE TABLE IF NOT EXISTS exit_health (
    exit_id    TEXT PRIMARY KEY REFERENCES exits(id) ON DELETE CASCADE,
    status     TEXT NOT NULL DEFAULT 'unknown',
    latency_ms REAL,
    checked_at TEXT
);

CREATE TABLE IF NOT EXISTS domain_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    domains TEXT NOT NULL,
    exit_id TEXT NOT NULL REFERENCES exits(id),
    fallback_override_id TEXT REFERENCES exits(id),
    ospf_distribute INTEGER NOT NULL DEFAULT 0,
    static_cidrs TEXT NOT NULL DEFAULT '[]',   -- JSON array of stable prefixes (corp OSPF + rule ipset)
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resolved_ips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_rule_id INTEGER NOT NULL REFERENCES domain_rules(id) ON DELETE CASCADE,
    ip TEXT NOT NULL,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(domain_rule_id, ip)
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    action TEXT NOT NULL,
    domain_rule_id INTEGER REFERENCES domain_rules(id) ON DELETE SET NULL,
    exit_id TEXT,
    detail TEXT,
    actor_ip TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS service_library (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domains TEXT NOT NULL,
    cidrs TEXT NOT NULL DEFAULT '[]',          -- JSON array of stable prefixes copied into a rule's static_cidrs
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    private_key TEXT NOT NULL,
    psk TEXT NOT NULL,
    address TEXT NOT NULL UNIQUE,     -- tunnel IP, no mask
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT
);
"""

async def open_db(path: str | None = None, autocommit: bool = False) -> aiosqlite.Connection:
    db_path = path or get_config().db_path
    # autocommit=True -> sqlite3 autocommit (isolation_level=None): each write
    # commits immediately and releases the WAL write lock between statements.
    # The sync daemon needs this -- it interleaves DB writes with multi-second
    # DNS resolution and ipset/ip/FRR/dnsmasq subprocess calls, and in the
    # default deferred-transaction mode the first INSERT holds the WAL write lock
    # until the final commit, so a concurrent panel save waits out busy_timeout
    # and fails with "database is locked". Set at connect() time, not via the
    # .isolation_level setter (which touches the sqlite3 object from the wrong
    # thread under aiosqlite and raises ProgrammingError).
    db = await aiosqlite.connect(db_path, isolation_level=None if autocommit else "")
    db.row_factory = aiosqlite.Row
    # Concurrency: panel + daemon write the same file. WAL allows a writer and
    # readers to coexist; busy_timeout makes the second writer wait instead of
    # failing with "database is locked". foreign_keys is per-connection.
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=15000")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.executescript(SCHEMA)
    # Lightweight migrations for databases created before a column existed.
    async with db.execute("PRAGMA table_info(exits)") as cur:
        cols = {r["name"] for r in await cur.fetchall()}
    if "type" not in cols:
        await db.execute("ALTER TABLE exits ADD COLUMN type TEXT NOT NULL DEFAULT 'manual'")
    # A concurrent import must not allocate the same fwmark twice (SELECT MAX+1
    # races across connections). Partial index: direct exits legitimately share 0.
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_exits_fwmark ON exits(fwmark) WHERE fwmark != 0")
    await db.commit()
    return db
