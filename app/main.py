import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api_routes import router as api_router
from app.jobs import init_db

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.base_dir = BASE_DIR
    init_db(BASE_DIR)
    logging.getLogger(__name__).info("应用启动 base_dir=%s", BASE_DIR)
    yield


app = FastAPI(title="万邑通 SKU 匹配", lifespan=lifespan)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def disable_cache_for_api(request, call_next):
    """避免 GET /api/* 被浏览器或 CDN 缓存成旧数据（匹配后列表不刷新）。"""
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
