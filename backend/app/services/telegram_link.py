"""Привязка Telegram без ручного ввода id.

- Пользователь: в панели получает ссылку t.me/<бот>?start=<код>, нажимает Start — его telegram id
  записывается в профиль. Так нельзя создать нового администратора основной команды.
- Чат для напоминаний: админ получает код, отправляет в группе `/bind <код>` — чат запоминается
  на его команду. Код одноразовый и живёт 15 минут. Отправитель должен быть этим администратором.
- Вход в панель песочницы: одноразовая magic-ссылка (purpose=magic).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import Conflict, Forbidden, ValidationError
from app.models import Role, Team, TeamKind, TelegramLinkCode, User
from app.repositories.teams import TeamRepository
from app.repositories.users import UserRepository
from app.services.audit import AuditService

CODE_TTL = timedelta(minutes=15)


@dataclass
class BoundChat:
    chat_id: str | None
    title: str | None
    source: str  # bind | env | none


def magic_url(settings: Settings, code: str) -> str:
    base = (settings.public_base_url or "http://localhost:8000").rstrip("/")
    return f"{base}/api/v1/auth/magic/{code}"


def get_bound_chat(db: DbSession, settings: Settings, team: Team | None = None) -> BoundChat:
    """Чат команды. Без team — основная (так worker и старые вызовы видят демо-чат)."""
    if team is None:
        team = TeamRepository(db).get_primary()
    if team is None:
        if settings.telegram_chat_id:
            return BoundChat(settings.telegram_chat_id, None, "env")
        return BoundChat(None, None, "none")
    if team.telegram_chat_id is not None:
        source = "bind" if team.chat_bound_by is not None else "env"
        return BoundChat(str(team.telegram_chat_id), team.telegram_chat_title, source)
    if team.kind == TeamKind.PRIMARY and settings.telegram_chat_id:
        return BoundChat(settings.telegram_chat_id, None, "env")
    return BoundChat(None, None, "none")


def chat_provider(session_factory, settings: Settings):
    def provider() -> str | None:
        with session_factory() as db:
            return get_bound_chat(db, settings).chat_id

    return provider


class TelegramLinkService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings

    def _new_code(self, purpose: str, user: User, ttl: timedelta) -> TelegramLinkCode:
        now = self.clock.now()
        code = TelegramLinkCode(
            code=secrets.token_urlsafe(12).replace("-", "x").replace("_", "y"),
            purpose=purpose,
            user_id=user.id,
            created_at=now,
            expires_at=now + ttl,
        )
        self.db.add(code)
        self.db.commit()
        return code

    def create_user_code(self, user: User) -> TelegramLinkCode:
        return self._new_code("user", user, CODE_TTL)

    def create_chat_code(self, admin: User) -> TelegramLinkCode:
        return self._new_code("chat", admin, CODE_TTL)

    def create_magic(self, user: User, ttl: timedelta) -> TelegramLinkCode:
        return self._new_code("magic", user, ttl)

    def _take(self, code: str, purpose: str) -> TelegramLinkCode:
        row = self.db.scalar(
            select(TelegramLinkCode).where(TelegramLinkCode.code == code.strip()).with_for_update()
        )
        if purpose == "magic":
            missing, used, expired = (
                "Ссылка недействительна",
                "Ссылка уже использована",
                "Срок ссылки истёк",
            )
        else:
            missing, used, expired = (
                "Код не найден. Получите новый в панели.",
                "Код уже использован. Получите новый в панели.",
                "Срок кода истёк (15 минут). Получите новый в панели.",
            )
        if row is None or row.purpose != purpose:
            raise ValidationError(missing)
        if row.used_at is not None:
            raise ValidationError(used)
        if row.expires_at < self.clock.now():
            raise ValidationError(expired)
        row.used_at = self.clock.now()
        return row

    def link_user(self, code: str, telegram_user_id: int) -> User:
        """Привязывает Telegram к уже существующему пользователю. Новых учёток не создаёт."""
        row = self._take(code, "user")
        users = UserRepository(self.db)
        user = users.get(row.user_id) if row.user_id else None
        if user is None:
            raise ValidationError("Пользователь для этого кода не найден")
        other = users.get_by_telegram_id(telegram_user_id)
        if other is not None and other.id != user.id:
            raise Conflict(f"Этот Telegram уже привязан к пользователю {other.login}")
        before = user.telegram_user_id
        user.telegram_user_id = telegram_user_id
        AuditService(self.db, self.clock).log(
            "telegram.user_linked",
            entity_type="user",
            entity_id=user.id,
            before={"telegram_user_id": before},
            after={"telegram_user_id": telegram_user_id},
            actor=user,
        )
        self.db.commit()
        return user

    def consume_magic(self, code: str) -> User:
        row = self._take(code, "magic")
        user = UserRepository(self.db).get(row.user_id) if row.user_id else None
        if user is None:
            raise ValidationError("Ссылка недействительна")
        team = user.team
        if team is not None and team.kind == TeamKind.SANDBOX and team.expires_at and team.expires_at <= self.clock.now():
            raise ValidationError("Срок временной команды истёк")
        return user

    def bind_chat(self, code: str, chat_id: int, title: str | None, sender_telegram_id: int | None) -> User:
        row = self._take(code, "chat")
        users = UserRepository(self.db)
        admin = users.get(row.user_id) if row.user_id else None
        if admin is None or admin.role != Role.ADMIN:
            raise Forbidden("Привязать группу может только администратор команды")
        if sender_telegram_id is None or admin.telegram_user_id is None or int(admin.telegram_user_id) != int(sender_telegram_id):
            raise Forbidden("Привязать группу может только администратор этой команды. Сначала привяжите свой Telegram.")
        team = admin.team
        teams = TeamRepository(self.db)
        self._reject_foreign_chat(team, int(chat_id), teams)
        if (
            team.telegram_chat_id is not None
            and team.chat_bound_by is not None
            and team.chat_bound_by != admin.id
            and int(team.telegram_chat_id) != int(chat_id)
        ):
            raise Forbidden("Перепривязать чат может только администратор, который его подключил")
        before = get_bound_chat(self.db, self.settings, team)
        team.telegram_chat_id = int(chat_id)
        team.telegram_chat_title = title or str(chat_id)
        team.chat_bound_by = admin.id
        AuditService(self.db, self.clock).log(
            "telegram.chat_bound",
            entity_type="telegram_chat",
            entity_id=chat_id,
            before={"chat_id": before.chat_id, "title": before.title},
            after={"chat_id": str(chat_id), "title": title},
            actor=admin,
        )
        self.db.commit()
        return admin

    def _reject_foreign_chat(self, team: Team, chat_id: int, teams: TeamRepository) -> None:
        primary = teams.get_primary()
        primary_ids = set()
        if self.settings.telegram_chat_id and str(self.settings.telegram_chat_id).lstrip("-").isdigit():
            primary_ids.add(int(self.settings.telegram_chat_id))
        if primary is not None and primary.telegram_chat_id is not None:
            primary_ids.add(int(primary.telegram_chat_id))
        if team.kind == TeamKind.SANDBOX and chat_id in primary_ids:
            raise ValidationError("Песочница не может использовать основной чат напоминаний")
        other = teams.get_by_chat_id(chat_id)
        if other is not None and other.id != team.id:
            raise Conflict("Этот чат уже привязан к другой команде")

    def unlink_user(self, user: User) -> None:
        before = user.telegram_user_id
        user.telegram_user_id = None
        AuditService(self.db, self.clock).log(
            "telegram.user_unlinked", entity_type="user", entity_id=user.id,
            before={"telegram_user_id": before}, after={"telegram_user_id": None}, actor=user,
        )
        self.db.commit()
