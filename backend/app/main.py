"""Создание FastAPI-приложения: роутеры, обработчики ошибок, статика SPA."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import install_error_handlers
from app.api.v1 import router as v1_router
from app.container import Container, build_container
from app.infrastructure.logging import request_id_var, setup_logging
from app.infrastructure.request_context import RequestContext, request_context

API_PREFIX = "/api/v1"

log = logging.getLogger("app")


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    setup_logging(container.settings.log_level)

    app = FastAPI(
        title="Invoice Keeper API",
        version="1.0.0",
        description=(
            "Напоминания о регулярных платежах. Авторизация: cookie-сессия (веб-панель) "
            "или `Authorization: Bearer <token>` — нажмите **Authorize** и введите логин/пароль."
        ),
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.state.container = container
    install_error_handlers(app)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        ctx_token = request_context.set(
            RequestContext(
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
            request_context.reset(ctx_token)
        response.headers["X-Request-ID"] = rid
        return response

    app.include_router(v1_router, prefix=API_PREFIX)
    _mount_spa(app, Path(container.settings.static_dir))
    return app


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    if not index.exists():
        return
    assets = static_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404, content={"error": {"code": "not_found", "message": "Не найдено", "details": None}}
            )
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


_app: FastAPI | None = None


def __getattr__(name: str):
    """`uvicorn app.main:app` — приложение создаётся лениво, чтобы импорт модуля не требовал .env."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
