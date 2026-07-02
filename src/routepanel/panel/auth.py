# src/routepanel/panel/auth.py
"""Password + session auth. Single admin password, stored as a PBKDF2 line in
cfg.password_file (created by the installer / routepanel-passwd). The session
cookie is an HMAC over an expiry timestamp, keyed off the stored hash line --
so changing the password invalidates every session, and no separate session
secret has to be stored or rotated."""
import hashlib, hmac, os, secrets, time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

ITERATIONS = 600_000
COOKIE = "rp_session"
EXEMPT_PREFIXES = ("/login", "/static", "/health")

def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${dk.hex()}"

def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, iters, salt, want = stored.strip().split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
        return algo == "pbkdf2_sha256" and hmac.compare_digest(dk.hex(), want)
    except (ValueError, AttributeError):
        return False

def read_password_file(path: str) -> str | None:
    try:
        with open(path) as f:
            line = f.read().strip()
        return line or None
    except OSError:
        return None

def _key(stored_hash: str) -> bytes:
    return hashlib.sha256(("session:" + stored_hash).encode()).digest()

def make_session(stored_hash: str, ttl_sec: int = 30 * 86400) -> str:
    exp = str(int(time.time()) + ttl_sec)
    sig = hmac.new(_key(stored_hash), exp.encode(), "sha256").hexdigest()
    return f"{exp}.{sig}"

def check_session(token: str, stored_hash: str) -> bool:
    try:
        exp, sig = token.split(".", 1)
        want = hmac.new(_key(stored_hash), exp.encode(), "sha256").hexdigest()
        return hmac.compare_digest(sig, want) and int(exp) > time.time()
    except (ValueError, AttributeError):
        return False

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from routepanel.config import get_config
        if request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)
        stored = read_password_file(get_config().password_file)
        if stored is None:      # no password file -> auth disabled (installer always creates one)
            return await call_next(request)
        tok = request.cookies.get(COOKIE, "")
        if check_session(tok, stored):
            return await call_next(request)
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
