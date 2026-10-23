"""Доменные исключения. Единый обработчик превращает их в {"error": {...}} и HTTP-коды."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "error"
    http_status = 400

    def __init__(self, message: str, *, details: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class NotFound(DomainError):
    code = "not_found"
    http_status = 404


class Unauthorized(DomainError):
    code = "unauthorized"
    http_status = 401


class Forbidden(DomainError):
    code = "forbidden"
    http_status = 403


class Conflict(DomainError):
    code = "conflict"
    http_status = 409


class ValidationError(DomainError):
    code = "validation_error"
    http_status = 422


class TooManyRequests(DomainError):
    code = "too_many_requests"
    http_status = 429
