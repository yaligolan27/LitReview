"""M7 — shared-access-code authentication for the web app.

Model (Maya's choice): one access code (``SURVEY_ACCESS_CODE``) shared with
the team. An empty code (the default) disables the whole layer, so local
development, the CLI and every existing test are untouched.

Mechanics — stdlib only, no new dependencies:

* Login exchanges the code for a signed session cookie
  ``exp_ts.hmac_sha256(key, exp_ts)``, where the key is derived from the
  access code. Rotating the code therefore invalidates every session — the
  natural "kick everyone out" lever for a shared-code model.
* The middleware guards everything except the login page, the auth
  endpoints and ``/api/health``: API requests get 401 JSON, page requests
  are redirected to ``/login.html``.
* A per-IP lockout (10 failures / 15 minutes → 429) blunts brute-forcing
  the code. In-memory and per-process — documented, and acceptable for the
  single-process deployments this app targets.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..config import get_settings

SESSION_TTL_SECONDS = 30 * 24 * 3600      # 30 days
COOKIE_NAME = "litreview_auth"
MAX_FAILURES = 10
LOCKOUT_WINDOW = 15 * 60                  # seconds

# Reachable without a session. /api/auth/login+status must be open so the
# login page can work; /api/health so platform healthchecks pass.
_OPEN_PATHS = {"/login.html", "/api/health",
               "/api/auth/login", "/api/auth/logout", "/api/auth/status"}

router = APIRouter()

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def enabled() -> bool:
    return bool(get_settings().access_code)


def _key() -> bytes:
    return hashlib.sha256(b"litreview-auth-v1:"
                          + get_settings().access_code.encode("utf-8")).digest()


def _sign(exp_ts: str) -> str:
    return hmac.new(_key(), exp_ts.encode("ascii"), hashlib.sha256).hexdigest()


def issue_token(now: float | None = None) -> str:
    exp = str(int((now or time.time()) + SESSION_TTL_SECONDS))
    return f"{exp}.{_sign(exp)}"


def token_valid(token: str, now: float | None = None) -> bool:
    exp, _, sig = (token or "").partition(".")
    if not exp.isdigit() or not sig:
        return False
    if int(exp) < (now or time.time()):
        return False
    return hmac.compare_digest(sig, _sign(exp))


# --- brute-force lockout ----------------------------------------------------


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _locked_out(ip: str, now: float | None = None) -> bool:
    now = now or time.time()
    with _failures_lock:
        recent = [t for t in _failures.get(ip, []) if now - t < LOCKOUT_WINDOW]
        _failures[ip] = recent
        return len(recent) >= MAX_FAILURES


def _record_failure(ip: str, now: float | None = None) -> None:
    with _failures_lock:
        _failures.setdefault(ip, []).append(now or time.time())


def _clear_failures(ip: str) -> None:
    with _failures_lock:
        _failures.pop(ip, None)


def reset_lockouts() -> None:
    """Test hook."""
    with _failures_lock:
        _failures.clear()


# --- endpoints --------------------------------------------------------------


def _secure_cookie(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


@router.get("/auth/status")
def auth_status(request: Request):
    return {"enabled": enabled(),
            "authenticated": (not enabled())
            or token_valid(request.cookies.get(COOKIE_NAME, ""))}


@router.post("/auth/login")
async def login(request: Request):
    if not enabled():
        return JSONResponse({"detail": "אימות אינו פעיל בשרת זה"}, status_code=400)
    ip = _client_ip(request)
    if _locked_out(ip):
        return JSONResponse(
            {"detail": "יותר מדי ניסיונות כושלים — נסה שוב בעוד רבע שעה"},
            status_code=429)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — malformed body is just a bad attempt
        body = {}
    code = str((body or {}).get("code", ""))
    if not secrets.compare_digest(code, get_settings().access_code):
        _record_failure(ip)
        return JSONResponse({"detail": "קוד גישה שגוי"}, status_code=401)
    _clear_failures(ip)
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE_NAME, issue_token(), max_age=SESSION_TTL_SECONDS, path="/",
        httponly=True, samesite="lax", secure=_secure_cookie(request))
    return response


@router.post("/auth/logout")
def logout(request: Request):
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# --- middleware -------------------------------------------------------------


def install_auth(app) -> None:
    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if not enabled():
            return await call_next(request)
        path = request.url.path.rstrip("/") or "/"
        if path in _OPEN_PATHS:
            return await call_next(request)
        if token_valid(request.cookies.get(COOKIE_NAME, "")):
            return await call_next(request)
        if path == "/api" or path.startswith("/api/"):
            return JSONResponse({"detail": "נדרשת התחברות"}, status_code=401)
        return RedirectResponse("/login.html", status_code=302)
