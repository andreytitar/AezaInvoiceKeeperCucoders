"""Зависимости роутеров: БД, сервисы, текущий пользователь, проверка ролей и CSRF."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session as DbSession

from app.container import Container
from app.domain.errors import Forbidden, Unauthorized
from app.models import Role, Session, User
from app.services.auth import AuthService

SESSION_COOKIE = "ik_session"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
    description="Логин и пароль; токен передаётся в заголовке Authorization: Bearer",
)


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_db(c: ContainerDep) -> Iterator[DbSession]:
    db = c.session_factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


DbDep = Annotated[DbSession, Depends(get_db)]


@dataclass
class CurrentAuth:
    user: User
    session: Session
    via_cookie: bool


def _origin_matches_host(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        # не браузер (curl, скрипты): CSRF неприменим
        return True
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return urlsplit(source).netloc.lower() == host.split(",")[0].strip().lower()


def get_auth(
    request: Request,
    c: ContainerDep,
    db: DbDep,
    bearer: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> CurrentAuth:
    token = bearer
    via_cookie = False
    if not token:
        token = request.cookies.get(SESSION_COOKIE)
        via_cookie = token is not None
    if not token:
        raise Unauthorized("Требуется авторизация")
    user, session = AuthService(db, c.clock, c.settings).authenticate(token)
    if via_cookie and request.method in UNSAFE_METHODS and not _origin_matches_host(request):
        raise Forbidden("Запрос с чужого источника отклонён (CSRF)", code="csrf_failed")
    request.state.user = user
    return CurrentAuth(user=user, session=session, via_cookie=via_cookie)


AuthDep = Annotated[CurrentAuth, Depends(get_auth)]


def require_user(auth: AuthDep) -> User:
    return auth.user


def require_admin(auth: AuthDep) -> User:
    if auth.user.role != Role.ADMIN:
        raise Forbidden("Действие доступно только администратору")
    return auth.user


UserDep = Annotated[User, Depends(require_user)]
AdminDep = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
