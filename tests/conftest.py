# tests/conftest.py
import pytest, aiosqlite
from routepanel.db import open_db

@pytest.fixture
async def tmp_db(tmp_path):
    db = await open_db(str(tmp_path / "test.db"))
    yield db
    await db.close()
