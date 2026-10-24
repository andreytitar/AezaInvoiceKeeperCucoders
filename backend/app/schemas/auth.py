from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import InputModel, OutputModel
from app.schemas.users import MeOut


class LoginRequest(InputModel):
    login: str = Field(min_length=1, max_length=64, examples=["admin"])
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(OutputModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    user: MeOut


class TelegramWidgetAuth(BaseModel):
    """Поля Telegram Login Widget. Лишние ключи сохраняются: они входят в подпись."""

    model_config = ConfigDict(extra="allow")

    id: int = Field(gt=0, description="Telegram user id из виджета, не ввод с клавиатуры")
    auth_date: int = Field(gt=0)
    hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    username: str | None = Field(default=None, max_length=64)
    photo_url: str | None = Field(default=None, max_length=1024)


class TelegramLoginConfig(OutputModel):
    enabled: bool
    bot_username: str | None = None
    token_configured: bool = False


class TelegramDeepLinkOut(OutputModel):
    code: str
    url: str
    expires_at: datetime


class TelegramPendingOut(OutputModel):
    pending: bool


class TelegramLoginResponse(OutputModel):
    status: Literal["authenticated", "unlinked", "waiting"]
    access_token: str | None = None
    token_type: str = "bearer"
    user: MeOut | None = None


class InviteCodeRequest(InputModel):
    code: str = Field(min_length=1, max_length=32)
