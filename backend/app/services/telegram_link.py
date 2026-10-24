"""Привязка Telegram без ручного ввода id.

- Пользователь: в панели получает ссылку t.me/<бот>?start=<код>, нажимает Start — его telegram id
  записывается в профиль.
- Чат для напоминаний: админ получает код, отправляет в группе `/bind <код>` — чат запоминается
  (перекрывает TELEGRAM_CHAT_ID из .env).
Коды одноразовые и живут 15 минут.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import Conflict, ValidationError
from app.models import AppMeta, TelegramLinkCode, User
from app.repositories.users import UserRepository
from app.services.audit import AuditService

CODE_TTL = timedelta(minutes=15)
CHAT_ID_KEY = "telegram_chat_id"
CHAT_TITLE_KEY = "telegram_chat_title"


@dataclass
class BoundChat:
    chat_id: str | None
    title: str | None
    source: str  # bind | env | none


def get_bound_chat(db: DbSession, settings: Settings) -> BoundChat:
    row = db.get(AppMeta, CHAT_ID_KEY)
    if row and row.value:
        title = db.get(AppMeta, CHAT_TITLE_KEY)
        return BoundChat(row.value, title.value if title else None, "bind")
    if settings.telegram_chat_id:
        return BoundChat(settings.telegram_chat_id, None, "env")
    return BoundChat(None, None, "none")


def chat_provider(session_factory, settings: Settings):
    def provider() -> str | None:
        with session_factory() as db:
            return get_bound_chat(db, settings).chat_id

    return provider


def _set_meta(db: DbSession, key: str, value: str) -> None:
    stmt = insert(AppMeta).values(key=key, value=value)
    db.execute(stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value}))


class TelegramLinkService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings

    def _new_code(self, purpose: str, user: User) -> TelegramLinkCode:
        now = self.clock.now()
        code = TelegramLinkCode(
            code=secrets.token_urlsafe(12).replace("-", "x").replace("_", "y"),
            purpose=purpose,
            user_id=user.id,
            created_at=now,
            expires_at=now + CODE_TTL,
        )
        self.db.add(code)
        self.db.commit()
        return code

    def create_user_code(self, user: User) -> TelegramLinkCode:
        return self._new_code("user", user)

    def create_chat_code(self, admin: User) -> TelegramLinkCode:
        return self._new_code("chat", admin)

    def _take(self, code: str, purpose: str) -> TelegramLinkCode:
        row = self.db.scalar(
            select(TelegramLinkCode).where(TelegramLinkCode.code == code.strip()).with_for_update()
        )
        if row is None or row.purpose != purpose:
            raise ValidationError("Код не найден. Получите новый в панели.")
        if row.used_at is not None:
            raise ValidationError("Код уже использован. Получите новый в панели.")
        if row.expires_at < self.clock.now():
            raise ValidationError("Срок кода истёк (15 минут). Получите новый в панели.")
        row.used_at = self.clock.now()
        return row

    def link_user(self, code: str, telegram_user_id: int) -> User:
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

    def bind_chat(self, code: str, chat_id: int, title: str | None) -> User | None:
        row = self._take(code, "chat")
        admin = UserRepository(self.db).get(row.user_id) if row.user_id else None
        before = get_bound_chat(self.db, self.settings)
        _set_meta(self.db, CHAT_ID_KEY, str(chat_id))
        _set_meta(self.db, CHAT_TITLE_KEY, title or str(chat_id))
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

    def unlink_user(self, user: User) -> None:
        before = user.telegram_user_id
        user.telegram_user_id = None
        AuditService(self.db, self.clock).log(
            "telegram.user_unlinked", entity_type="user", entity_id=user.id,
            before={"telegram_user_id": before}, after={"telegram_user_id": None}, actor=user,
        )
        self.db.commit()
