"""Управление обычными пользователями (только admin). Системный админ через API не управляется."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import Conflict, Forbidden, NotFound
from app.infrastructure.security import hash_password
from app.models import Role, User
from app.repositories.users import SessionRepository, UserRepository

_UNSET = object()


class UserService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def list(self) -> list[User]:
        return self.users.list_regular()

    def _ensure_login_free(self, login: str, exclude: uuid.UUID | None = None) -> None:
        if login.lower() == self.settings.admin_login.lower():
            raise Conflict("Логин зарезервирован системным администратором", code="login_taken")
        existing = self.users.get_by_login(login)
        if existing is not None and existing.id != exclude:
            raise Conflict("Пользователь с таким логином уже существует", code="login_taken")

    def _ensure_telegram_free(self, telegram_user_id: int | None, exclude: uuid.UUID | None = None) -> None:
        if telegram_user_id is None:
            return
        existing = self.users.get_by_telegram_id(telegram_user_id)
        if existing is not None and existing.id != exclude:
            raise Conflict("Этот Telegram-аккаунт уже привязан к другому пользователю", code="telegram_taken")

    def _get_manageable(self, user_id: uuid.UUID) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise NotFound("Пользователь не найден")
        if user.is_system:
            raise Forbidden("Системный администратор управляется только через .env", code="system_user")
        return user

    def create(self, *, login: str, password: str, email: str | None = None, telegram_user_id: int | None = None) -> User:
        self._ensure_login_free(login)
        self._ensure_telegram_free(telegram_user_id)
        user = self.users.add(
            User(
                login=login,
                password_hash=hash_password(password),
                role=Role.USER,  # через API создаётся только обычный пользователь
                is_system=False,
                email=email,
                telegram_user_id=telegram_user_id,
            )
        )
        self.db.commit()
        return user

    def update(
        self,
        user_id: uuid.UUID,
        *,
        login=_UNSET,
        password=_UNSET,
        email=_UNSET,
        telegram_user_id=_UNSET,
    ) -> User:
        user = self._get_manageable(user_id)
        revoke = False
        if login is not _UNSET and login != user.login:
            self._ensure_login_free(login, exclude=user.id)
            user.login = login
        if password is not _UNSET:
            user.password_hash = hash_password(password)
            revoke = True
        if email is not _UNSET:
            user.email = email
        if telegram_user_id is not _UNSET:
            self._ensure_telegram_free(telegram_user_id, exclude=user.id)
            user.telegram_user_id = telegram_user_id
        if revoke:
            self.sessions.revoke_all_for_user(user.id, self.clock.now())
        self.db.commit()
        return user

    def delete(self, user_id: uuid.UUID) -> None:
        user = self._get_manageable(user_id)
        now = self.clock.now()
        user.deleted_at = now
        self.sessions.revoke_all_for_user(user.id, now)
        self.db.commit()
