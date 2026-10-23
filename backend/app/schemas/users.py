from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.models import Role
from app.schemas.common import InputModel, OutputModel

Login = Annotated[str, Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$", examples=["ivan"])]
Password = Annotated[str, Field(min_length=6, max_length=128)]
Email = Annotated[str, Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", examples=["ivan@example.com"])]
TelegramUserId = Annotated[int, Field(gt=0, description="Числовой id Telegram-аккаунта (для кнопки «Оплачено»)")]


class UserOut(OutputModel):
    id: uuid.UUID
    login: str
    role: Role
    email: str | None
    telegram_user_id: int | None
    created_at: datetime


class MeOut(UserOut):
    is_system: bool


class UserCreate(InputModel):
    """Роль не передаётся: через API создаётся только пользователь с ролью `user`."""

    login: Login
    password: Password
    email: Email | None = None
    telegram_user_id: TelegramUserId | None = None


class UserUpdate(InputModel):
    """Частичное обновление. Смена пароля завершает все сессии пользователя."""

    login: Login | None = None
    password: Password | None = None
    email: Email | None = None
    telegram_user_id: TelegramUserId | None = None
