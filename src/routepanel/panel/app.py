# src/routepanel/panel/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from routepanel.panel.routes import domains, exits, library, history, clients

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
app.include_router(clients.router)
app.include_router(library.router)
app.include_router(history.router)

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from routepanel.panel import auth as _auth
from routepanel.panel._templates import templates

app.add_middleware(_auth.AuthMiddleware)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": ""})

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    from routepanel.config import get_config
    stored = _auth.read_password_file(get_config().password_file)
    if stored is None or not _auth.verify_password(password, stored):
        return JSONResponse({"detail": "wrong password"}, status_code=401)
    resp = RedirectResponse("/", status_code=303)
    # No secure=True: the panel serves plain HTTP on 127.0.0.1 (ssh -L access
    # model), where the flag would break login. Revisit if TLS/public bind lands.
    resp.set_cookie(_auth.COOKIE, _auth.make_session(stored),
                    httponly=True, samesite="lax", max_age=30 * 86400)
    return resp

def main() -> None:
    import uvicorn
    from routepanel.config import get_config
    cfg = get_config()
    uvicorn.run("routepanel.panel.app:app", host=cfg.bind_host, port=cfg.port, reload=False)
