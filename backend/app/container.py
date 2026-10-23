"""Композиция зависимостей: настройки, часы, БД, каналы уведомлений.

API и worker собирают один и тот же контейнер; тесты подменяют часы и каналы фейками.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_session_factory
from app.domain.clock import Clock, SystemClock
from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.registry import build_channels
from app.infrastructure.rate_limit import LoginRateLimiter


@dataclass
class Container:
    settings: Settings
    clock: Clock
    session_factory: sessionmaker[Session]
    rate_limiter: LoginRateLimiter
    channels: ChannelRegistry = field(default_factory=ChannelRegistry)
    extras: dict = field(default_factory=dict)


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    return Container(
        settings=settings,
        clock=SystemClock(settings.tz, settings.app_fake_today),
        session_factory=get_session_factory(),
        rate_limiter=LoginRateLimiter(settings.login_rate_limit_attempts, settings.login_rate_limit_window_seconds),
        channels=build_channels(settings),
    )
