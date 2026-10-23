"""Единый формат ошибок: {"error": {"code", "message", "details"}}. Без стектрейсов наружу."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DomainError

log = logging.getLogger("app.errors")

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_response(status: int, code: str, message: str, details: Any = None, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=headers,
    )


def _clean_validation_errors(errors: list[dict]) -> list[dict]:
    cleaned = []
    for e in errors:
        item = {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
        cleaned.append(item)
    return cleaned


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return error_response(exc.http_status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return error_response(422, "validation_error", "Некорректные данные запроса", _clean_validation_errors(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else code
        return error_response(exc.status_code, code, message, None, getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Необработанная ошибка: %s", type(exc).__name__)
        return error_response(500, "internal_error", "Внутренняя ошибка сервера")


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Не авторизован"},
    403: {"model": ErrorResponse, "description": "Недостаточно прав"},
    404: {"model": ErrorResponse, "description": "Не найдено"},
    409: {"model": ErrorResponse, "description": "Конфликт"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации"},
}


def responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: ERROR_RESPONSES[c] for c in codes}
