"""Вход, сессии, выход и синхронизация системного администратора из .env."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import TooManyRequests, Unauthorized
from app.infrastructure.rate_limit import LoginRateLimiter
from app.infrastructure.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_session_token,
    verify_password,
)
from app.models import Role, Session, TeamKind, User
from app.repositories.teams import TeamRepository
from app.repositories.users import SessionRepository, UserRepository
from app.services.audit import AuditService
from app.services.telegram_link import TelegramLinkService

log = logging.getLogger("app.auth")


@dataclass
class LoginResult:
    user: User
    token: str
    session: Session


class AuthService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings, limiter: LoginRateLimiter | None = None):
        self.db = db
        self.clock = clock
        self.settings = settings
        self.limiter = limiter
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def login(self, login: str, password: str, ip: str = "unknown") -> LoginResult:
        user = self.authenticate_password(login, password, ip)
        result = self._open_session(user)
        log.info("Успешный вход", extra={"login": user.login, "ip": ip})
        return result

    def authenticate_password(self, login: str, password: str, ip: str = "unknown") -> User:
        """Проверяет логин и пароль и не открывает сессию. Неудача пишется в журнал сразу."""
        if self.limiter:
            retry = self.limiter.retry_after(ip, login)
            if retry is not None:
                AuditService(self.db, self.clock).log("auth.login_blocked", entity_type="user", actor_login=login[:64])
                self.db.commit()
                raise TooManyRequests(
                    "Слишком много неудачных попыток входа, попробуйте позже",
                    details={"retry_after_seconds": retry},
                )
        user = self.users.get_by_login(login)
        if not verify_password(user.password_hash if user else None, password) or user is None:
            if self.limiter:
                self.limiter.register_failure(ip, login)
            log.info("Неудачный вход", extra={"login": login, "ip": ip})
            AuditService(self.db, self.clock).log("auth.login_failed", entity_type="user", actor_login=login[:64])
            self.db.commit()
            raise Unauthorized("Неверный логин или пароль", code="invalid_credentials")
        if self.limiter:
            self.limiter.reset(ip, login)
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        return user

    def start_session(self, user: User, action: str = "auth.login") -> LoginResult:
        self._ensure_team_alive(user)
        return self._open_session(user, action=action)

    def login_magic(self, code: str) -> LoginResult:
        user = TelegramLinkService(self.db, self.clock, self.settings).consume_magic(code)
        self._ensure_team_alive(user)
        return self._open_session(user, action="auth.magic_login")

    def _open_session(self, user: User, action: str = "auth.login") -> LoginResult:
        now = self.clock.now()
        token = new_session_token()
        session = self.sessions.add(
            Session(
                user_id=user.id,
                token_hash=hash_token(token, self.settings.secret_key),
                created_at=now,
                expires_at=now + timedelta(hours=self.settings.session_ttl_hours),
                last_seen_at=now,
            )
        )
        AuditService(self.db, self.clock).log(action, entity_type="user", entity_id=user.id, actor=user)
        self.db.commit()
        return LoginResult(user=user, token=token, session=session)

    def _ensure_team_alive(self, user: User) -> None:
        team = user.team
        if team is not None and team.kind == TeamKind.SANDBOX and team.expires_at and team.expires_at <= self.clock.now():
            raise Unauthorized("Срок временной команды истёк")

    def authenticate(self, token: str) -> tuple[User, Session]:
        now = self.clock.now()
        session = self.sessions.get_active_by_hash(hash_token(token, self.settings.secret_key), now)
        if session is None:
            raise Unauthorized("Требуется авторизация")
        user = self.users.get(session.user_id)
        if user is None:
            raise Unauthorized("Требуется авторизация")
        team = user.team
        if team is not None and team.kind == TeamKind.SANDBOX and team.expires_at and team.expires_at <= now:
            raise Unauthorized("Срок временной команды истёк")
        if (now - session.last_seen_at).total_seconds() > 60:
            session.last_seen_at = now
            self.db.commit()
        return user, session

    def logout(self, session: Session) -> None:
        session.revoked_at = self.clock.now()
        AuditService(self.db, self.clock).log("auth.logout", entity_type="user", entity_id=session.user_id, actor=session.user)
        self.db.commit()

    def sync_system_admin(self) -> User:
        """Админ из .env: создаётся или обновляется при каждом старте. Смена пароля в .env
        действует после рестарта и ревокует старые сессии админа."""
        s = self.settings
        now = self.clock.now()
        primary = TeamRepository(self.db).ensure_primary()
        if s.telegram_chat_id and primary.telegram_chat_id is None:
            raw = str(s.telegram_chat_id).strip()
            if raw.lstrip("-").isdigit():
                primary.telegram_chat_id = int(raw)
                log.info("Основной команде назначен чат из TELEGRAM_CHAT_ID")
        for other in self.users.list_system():
            if other.login.lower() != s.admin_login.lower():
                other.deleted_at = now
                self.sessions.revoke_all_for_user(other.id, now)
                log.warning("Прежний системный администратор %s отключён (сменился ADMIN_LOGIN)", other.login)

        admin = self.users.get_by_login(s.admin_login)
        if admin is not None and not admin.is_system:
            # обычный пользователь с логином администратора: освобождаем логин
            admin.deleted_at = now
            self.sessions.revoke_all_for_user(admin.id, now)
            log.warning("Пользователь %s отключён: логин занят системным администратором", admin.login)
            self.db.flush()
            admin = None

        if admin is None:
            admin = self.users.add(
                User(
                    team_id=primary.id,
                    login=s.admin_login,
                    password_hash=hash_password(s.admin_password),
                    role=Role.ADMIN,
                    is_system=True,
                )
            )
            log.info("Системный администратор создан", extra={"login": s.admin_login})
        else:
            admin.team_id = primary.id
            admin.role = Role.ADMIN
            if not verify_password(admin.password_hash, s.admin_password):
                admin.password_hash = hash_password(s.admin_password)
                self.sessions.revoke_all_for_user(admin.id, now)
                log.info("Пароль системного администратора обновлён из .env")
        self.db.commit()
        return admin
