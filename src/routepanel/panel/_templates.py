# src/routepanel/panel/_templates.py
from pathlib import Path
from fastapi.templating import Jinja2Templates
import hashlib

_STATIC_DIR = Path(__file__).parent / "static"


def _static_version() -> str:
    """Short content hash of all static assets, for cache-busting ?v= query params.

    Computed once at import (the panel process restarts on every deploy), so the
    value changes whenever any static file changes, forcing browsers to refetch
    instead of serving a heuristically-cached stale copy (Starlette's StaticFiles
    sends no Cache-Control, so without this browsers keep old CSS/JS).
    """
    h = hashlib.md5()
    for f in sorted(_STATIC_DIR.glob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["static_ver"] = _static_version()
