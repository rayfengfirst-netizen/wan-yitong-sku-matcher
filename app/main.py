import hashlib
import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api_routes import router as api_router
from app.jobs import init_db

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── auth ──────────────────────────────────────────────────────────────
AUTH_USER = "admin"
AUTH_PASS = "huangzhu2019"
SESSION_COOKIE = "wyt_session"
SESSION_MAX_AGE = 86400 * 7
_session_secret = secrets.token_hex(32)


def _sign_session(payload: str) -> str:
    sig = hmac.new(_session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_session(token: str) -> bool:
    if not token or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(_session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        ts = int(payload.split("|")[1])
    except (IndexError, ValueError):
        return False
    return (time.time() - ts) < SESSION_MAX_AGE


_PUBLIC_PATHS = frozenset({"/health", "/api/login"})


# ── lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.base_dir = BASE_DIR
    init_db(BASE_DIR)
    logging.getLogger(__name__).info("应用启动 base_dir=%s", BASE_DIR)
    yield


app = FastAPI(title="万邑通 SKU 匹配", lifespan=lifespan)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── middleware: auth gate ─────────────────────────────────────────────
@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    if _verify_session(token):
        return await call_next(request)
    if path == "/":
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        resp = HTMLResponse(html)
        return resp
    return JSONResponse({"detail": "未登录，请先验证身份"}, status_code=401)


@app.middleware("http")
async def disable_cache_for_api(request, call_next):
    """避免 GET /api/* 被浏览器或 CDN 缓存成旧数据（匹配后列表不刷新）。"""
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.middleware("http")
async def short_cache_static_assets(request, call_next):
    """避免 app.js / styles.css 长期缓存导致用户一直用旧前端逻辑。"""
    response = await call_next(request)
    p = request.url.path
    if p.startswith("/static/") and (p.endswith(".js") or p.endswith(".css")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


# ── routes ────────────────────────────────────────────────────────────
@app.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()
    if username == AUTH_USER and password == AUTH_PASS:
        payload = f"{username}|{int(time.time())}"
        token = _sign_session(payload)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return resp
    return JSONResponse({"ok": False, "detail": "用户名或密码错误"}, status_code=401)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
