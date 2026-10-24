"""Куда уходит напоминание команды: группа, если привязана, иначе личка админа песочницы.

Одно напоминание — один получатель. Песочница не пишет в чат другой команды и в чат из TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import Role, Team, TeamKind, User, WebhookEndpoint

log = logging.getLogger("app.team_delivery")

DEAD_CHAT_MARKERS = (
    "chat not found",
    "bot was kicked",
    "kicked from",
    "bot is not a member",
    "forbidden",
    "have no rights to send",
    "not enough rights",
    "group chat was deactivated",
    "chat was deleted",
    "need administrator rights",
)


def is_dead_chat_error(error: str | None) -> bool:
    if not error:
        return False
    low = error.lower()
    return any(marker in low for marker in DEAD_CHAT_MARKERS)


def telegram_recipient(db: DbSession, team: Team) -> str | None:
    """Группа команды, если привязана. Иначе личка администратора песочницы. У основной без чата — никуда."""
    if team.telegram_chat_id is not None:
        return str(team.telegram_chat_id)
    if team.kind != TeamKind.SANDBOX:
        return None
    admin_tg = db.scalar(
        select(User.telegram_user_id).where(
            User.team_id == team.id,
            User.role == Role.ADMIN,
            User.deleted_at.is_(None),
            User.telegram_user_id.is_not(None),
        )
    )
    return str(admin_tg) if admin_tg is not None else None


def email_recipients(db: DbSession, settings: Settings, team: Team) -> list[str]:
    rows = db.scalars(
        select(User.email).where(User.team_id == team.id, User.deleted_at.is_(None), User.email.is_not(None))
    )
    result = [e for e in rows if e]
    if team.kind == TeamKind.PRIMARY and settings.email_to_users is not False:
        # статический список жюри — только основная команда, не песочницы
        result = list(settings.email_static_recipients) + result
    elif team.kind == TeamKind.PRIMARY:
        result = list(settings.email_static_recipients) + result
    seen: set[str] = set()
    out: list[str] = []
    for item in result:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    if team.kind != TeamKind.PRIMARY:
        # у песочницы нет общего списка из .env
        out = [e for e in out if e.lower() not in {s.lower() for s in settings.email_static_recipients}]
    return out


def webhook_recipients(db: DbSession, team: Team) -> list[str]:
    rows = db.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.team_id == team.id, WebhookEndpoint.is_active.is_(True))
    )
    return [str(e.id) for e in rows if "payment.reminder" in (e.events or [])]


def clear_dead_chat(db: DbSession, recipient: str) -> Team | None:
    """Снимает привязку, если получатель — чат команды, из которого бота выгнали."""
    try:
        chat_id = int(recipient)
    except (TypeError, ValueError):
        return None
    team = db.scalar(select(Team).where(Team.telegram_chat_id == chat_id))
    if team is None:
        return None
    log.warning(
        "Чат %s команды %s недоступен (%s), привязка снята",
        chat_id,
        team.id,
        team.kind.value,
    )
    team.telegram_chat_id = None
    team.telegram_chat_title = None
    team.chat_bound_by = None
    return team


def recipients_for(db: DbSession, settings: Settings, channel, occ) -> list[str]:
    """Получатели одной доставки. FakeChannel в тестах остаётся на своём recipients()."""
    payment = getattr(occ, "payment", None)
    team_id = getattr(payment, "team_id", None) if payment is not None else None
    team = db.get(Team, team_id) if team_id is not None else None
    name = getattr(channel, "name", "")
    kind = type(channel).__name__
    if team is not None and name == "telegram" and kind in ("TelegramChannel", "LogTelegramChannel"):
        recipient = telegram_recipient(db, team)
        return [recipient] if recipient else []
    if team is not None and name == "email":
        if not settings.email_to_users and team.kind != TeamKind.PRIMARY:
            return []
        if not settings.email_to_users and team.kind == TeamKind.PRIMARY:
            return _dedupe(settings.email_static_recipients)
        return email_recipients(db, settings, team)
    if team is not None and name == "webhook":
        return webhook_recipients(db, team)
    if team is not None and name == "chat":
        return channel.recipients() if team.kind == TeamKind.PRIMARY else []
    return channel.recipients()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
