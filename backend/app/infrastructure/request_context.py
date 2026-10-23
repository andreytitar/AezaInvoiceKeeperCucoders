"""Контекст текущего запроса для аудита: IP, user-agent, пользователь."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass
class RequestContext:
    ip: str | None = None
    user_agent: str | None = None
    actor_id: object | None = None
    actor_login: str | None = None


request_context: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar("request_context", default=None)


def current() -> RequestContext:
    return request_context.get() or RequestContext()
