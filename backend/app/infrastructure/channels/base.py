"""Интерфейс канала уведомлений. Новый канал = новый класс + регистрация в build_channels()."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Action:
    """Действие под сообщением (inline-кнопка в Telegram)."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class Notification:
    """Единый DTO уведомления. Обязательные поля текста: название, сумма, валюта, дата оплаты."""

    occurrence_id: uuid.UUID
    title: str
    amount: Decimal
    currency: str
    due_date: date
    kind: str = "reminder"
    days_until_due: int = 0
    actions: tuple[Action, ...] = field(default_factory=tuple)
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None
    external_id: str | None = None
    retryable: bool = True


@runtime_checkable
class NotificationChannel(Protocol):
    name: str

    async def send(self, message: Notification, recipient: str) -> SendResult: ...

    def recipients(self) -> list[str]: ...


class ChannelRegistry:
    def __init__(self, channels: list[NotificationChannel] | None = None) -> None:
        self._channels: dict[str, NotificationChannel] = {}
        for ch in channels or []:
            self.register(ch)

    def register(self, channel: NotificationChannel) -> None:
        self._channels[channel.name] = channel

    def get(self, name: str) -> NotificationChannel | None:
        return self._channels.get(name)

    def all(self) -> list[NotificationChannel]:
        return list(self._channels.values())

    def names(self) -> list[str]:
        return list(self._channels)
