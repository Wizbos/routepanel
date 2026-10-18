# tests/conftest.py
import pytest, aiosqlite
from routepanel.db import open_db

@pytest.fixture
async def tmp_db(tmp_path):
    db = await open_db(str(tmp_path / "test.db"))
    yield db
    await db.close()


@pytest.fixture(autouse=True)
def no_live_sync_signal(monkeypatch):
    """Never SIGUSR1 a real routesyncd: on the prod box /run/routesyncd.pid exists,
    and every API test that edits a rule used to trigger a live sync (~48/min).
    Yields the list of recorded trigger_sync calls."""
    calls = []
    for mod in ("routepanel.panel.routes.domains", "routepanel.panel.routes.exits"):
        monkeypatch.setattr(f"{mod}.trigger_sync", lambda: calls.append(1))
    return calls
