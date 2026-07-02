# tests/unit/test_db_concurrency.py
import pytest, aiosqlite
from routepanel.db import open_db


@pytest.mark.asyncio
async def test_autocommit_conn_does_not_hold_write_lock(tmp_path):
    """Regression for the 'database is locked' panel-save failure.

    The sync daemon opens its connection with autocommit=True so a write is
    committed immediately and the WAL write lock is released between statements.
    A second writer (the panel) must then be able to write without blocking,
    even while the daemon is mid-cycle between its own writes.
    """
    path = str(tmp_path / "c.db")
    daemon = await open_db(path, autocommit=True)
    panel = await open_db(path)
    await panel.execute("PRAGMA busy_timeout=300")  # fail fast if blocked
    try:
        # daemon writes (no explicit commit) -- simulates an in-loop INSERT
        await daemon.execute("INSERT INTO history(action,detail) VALUES('sync','daemon')")
        # panel must be able to write immediately: lock was released
        await panel.execute("INSERT INTO history(action,detail) VALUES('changed','panel')")
        await panel.commit()
        async with panel.execute("SELECT COUNT(*) FROM history") as cur:
            assert (await cur.fetchone())[0] == 2
    finally:
        await daemon.close()
        await panel.close()


@pytest.mark.asyncio
async def test_default_conn_holds_write_lock_until_commit(tmp_path):
    """Documents the bug the autocommit fix avoids: a default (deferred-txn)
    connection grabs the WAL write lock on its first write and holds it until
    commit, so a concurrent writer blocks and raises 'database is locked'."""
    path = str(tmp_path / "c.db")
    daemon = await open_db(path)  # default: deferred transaction, no autocommit
    panel = await open_db(path)
    await panel.execute("PRAGMA busy_timeout=300")
    try:
        await daemon.execute("INSERT INTO history(action,detail) VALUES('sync','daemon')")
        # daemon's write txn is still open -> panel is locked out
        with pytest.raises(aiosqlite.OperationalError):
            await panel.execute("INSERT INTO history(action,detail) VALUES('changed','panel')")
            await panel.commit()
    finally:
        await daemon.close()
        await panel.close()
