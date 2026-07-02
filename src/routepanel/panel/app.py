# src/routepanel/panel/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from routepanel.panel.routes import domains, exits, library, history

STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    from routepanel.db import open_db
    db = await open_db()
    await db.close()
    yield

app = FastAPI(lifespan=lifespan, title="routepanel")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(domains.router)
app.include_router(exits.router)
app.include_router(library.router)
app.include_router(history.router)

def main() -> None:
    import uvicorn
    from routepanel.config import get_config
    cfg = get_config()
    uvicorn.run("routepanel.panel.app:app", host=cfg.bind_host, port=cfg.port, reload=False)
