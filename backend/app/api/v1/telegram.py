from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.api.deps import AdminDep, ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.infrastructure.channels.telegram import TelegramClient, TelegramError
from app.services.telegram_link import TelegramLinkService, get_bound_chat

router = APIRouter(prefix="/telegram", tags=["telegram"])

log = logging.getLogger("app.telegram")
_bot_cache: dict[str, tuple[float, str]] = {}
_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{5,32}")


def normalize_bot_username(value: str | None) -> str | None:
    raw = (value or "").strip().lstrip("@")
    if _USERNAME_RE.fullmatch(raw):
        return raw
    return None


async def bot_username(c) -> str | None:
    """Имя бота для ссылки t.me/<бот>?start=… (getMe). Успех кэшируется на 10 минут, ошибка — нет."""
    s = c.settings
    if not s.telegram_enabled:
        return None
    token = s.telegram_bot_token or ""
    cached = _bot_cache.get(token)
    if cached and time.monotonic() - cached[0] < 600:
        return cached[1]
    try:
        me = await TelegramClient(token, s.telegram_api_base, timeout=5).get_me()
        name = normalize_bot_username(me.get("username") if isinstance(me, dict) else None)
    except TelegramError:
        log.warning("getMe не вернул имя бота")
        return None
    if not name:
        log.warning("getMe не вернул имя бота")
        return None
    _bot_cache[token] = (time.monotonic(), name)
    return name


async def login_bot_username(c) -> str | None:
    """Имя для кнопки входа: из настроек, а если его нет — через getMe по токену."""
    configured = normalize_bot_username(c.settings.telegram_login_bot)
    if configured:
        return configured
    return await bot_username(c)


class TelegramStatus(BaseModel):
    enabled: bool
    dry_run: bool
    bot_username: str | None
    chat_bound: bool
    chat_title: str | None
    chat_source: str
    me_linked: bool


class LinkCode(BaseModel):
    code: str
    command: str
    url: str | None
    expires_at: datetime


@router.get("/status", response_model=TelegramStatus, summary="Состояние Telegram-бота и привязок", responses=responses(401))
async def telegram_status(user: UserDep, c: ContainerDep, db: DbDep) -> TelegramStatus:
    chat = get_bound_chat(db, c.settings, user.team)
    return TelegramStatus(
        enabled=c.settings.telegram_enabled,
        dry_run=not c.settings.telegram_enabled,
        bot_username=await bot_username(c),
        chat_bound=chat.chat_id is not None,
        chat_title=chat.title if user.role == "admin" else None,
        chat_source=chat.source,
        me_linked=user.telegram_user_id is not None,
    )


@router.post(
    "/link",
    response_model=LinkCode,
    summary="Ссылка для привязки своего Telegram (одноразовая, 15 минут)",
    description="Откройте `url` (t.me/<бот>?start=<код>) и нажмите Start — telegram id запишется в профиль.",
    responses=responses(401),
)
async def link_me(user: UserDep, c: ContainerDep, db: DbDep) -> LinkCode:
    code = TelegramLinkService(db, c.clock, c.settings).create_user_code(user)
    name = await bot_username(c)
    return LinkCode(
        code=code.code,
        command=f"/start {code.code}",
        url=f"https://t.me/{name}?start={code.code}" if name else None,
        expires_at=code.expires_at,
    )


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT, summary="Отвязать свой Telegram", responses=responses(401))
def unlink_me(user: UserDep, c: ContainerDep, db: DbDep) -> Response:
    TelegramLinkService(db, c.clock, c.settings).unlink_user(db.merge(user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/chat-link",
    response_model=LinkCode,
    summary="Код подключения чата для напоминаний (admin)",
    description="Добавьте бота в группу и отправьте там `/bind <код>` — напоминания пойдут в эту группу.",
    responses=responses(401, 403),
)
async def chat_link(admin: AdminDep, c: ContainerDep, db: DbDep) -> LinkCode:
    code = TelegramLinkService(db, c.clock, c.settings).create_chat_code(admin)
    name = await bot_username(c)
    return LinkCode(
        code=code.code,
        command=f"/bind {code.code}",
        url=f"https://t.me/{name}?startgroup=bind" if name else None,
        expires_at=code.expires_at,
    )
