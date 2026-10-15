from __future__ import annotations

import argparse
import logging
import mimetypes
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.core.config import WEB_DIR, Settings, get_settings
from app.core.database import Database
from app.core.errors import AppError, install_exception_handlers
from app.core.security import SlidingWindowRateLimiter
from app.extensions import build_extensions
from app.routers import (
    ai,
    day,
    entries,
    images,
    memos,
    reminders,
    reports,
    routines,
    settings as settings_router,
    threads,
    timers,
)

logger = logging.getLogger(__name__)

_BODY_LIMIT_DEFAULT = 1 * 1024 * 1024
_BODY_LIMIT_IMAGES = 14 * 1024 * 1024
_TEXTUAL_TYPES = ("text/", "application/javascript", "application/json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.db = Database(settings.db_path)
    app.state.extensions = build_extensions(settings)
    app.state.rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="每日计划", lifespan=lifespan)
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(body_size_limit_middleware)
    app.middleware("http")(access_log_middleware)

    for router in (
        day.router,
        entries.router,
        timers.router,
        routines.router,
        threads.router,
        memos.router,
        reports.router,
        images.router,
        reminders.router,
        settings_router.router,
        ai.router,
    ):
        app.include_router(router)

    app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])(
        static_fallback
    )
    return app


async def body_size_limit_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        limit = (
            _BODY_LIMIT_IMAGES
            if request.url.path == "/api/images"
            else _BODY_LIMIT_DEFAULT
        )
        length = request.headers.get("content-length")
        if length is not None and int(length) > limit:
            return JSONResponse({"error": "内容过长"}, status_code=400)
    return await call_next(request)


async def access_log_middleware(request: Request, call_next):
    response = await call_next(request)
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


def _content_type(path: Path) -> str:
    media_type, _ = mimetypes.guess_type(str(path))
    media_type = media_type or "application/octet-stream"
    if media_type.startswith(_TEXTUAL_TYPES):
        media_type += "; charset=utf-8"
    return media_type


async def static_fallback(full_path: str, request: Request) -> Response:
    """非 API 路径：伺服 web/ 静态文件，缺失时回退 index.html（SPA）。"""
    if full_path.startswith("api/"):
        return JSONResponse({"error": "没有找到这个操作"}, status_code=404)
    target = (WEB_DIR / full_path.lstrip("/")).resolve() if full_path else WEB_DIR / "index.html"
    web_root = WEB_DIR.resolve()
    if not target.is_relative_to(web_root):
        raise AppError("没有找到这个页面", 404)
    if not target.is_file():
        target = web_root / "index.html"
    if not target.is_file():
        raise AppError("页面文件还没有准备好", 404)
    return Response(
        content=target.read_bytes(),
        media_type=_content_type(target),
        headers={"Cache-Control": "no-cache"},
    )


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="每日计划服务")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=settings.log_file,
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s %(levelname)s %(message)s",
    )
    port = args.port if args.port is not None else settings.port
    url = f"http://127.0.0.1:{port}"
    print(f"每日计划已启动：{url}")
    print(f"数据文件：{settings.db_path}")
    print("按 Ctrl+C 停止。数据已经保存在 SQLite 文件中。")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=settings.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
