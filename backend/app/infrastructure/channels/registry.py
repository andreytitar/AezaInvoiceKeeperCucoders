"""Сборка реестра каналов из конфигурации. Новый канал = класс с интерфейсом NotificationChannel
+ одна строка регистрации здесь."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.config import Settings
from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.email import EmailChannel
from app.infrastructure.channels.webhook import EndpointConfig, WebhookChannel
from app.infrastructure.channels.telegram import LogTelegramChannel, TelegramChannel, TelegramClient

log = logging.getLogger("app.channels")


def build_channels(
    settings: Settings,
    user_emails: Callable[[], list[str]] | None = None,
    webhook_endpoints: Callable[[], list[EndpointConfig]] | None = None,
    now_iso: Callable[[], str] | None = None,
) -> ChannelRegistry:
    registry = ChannelRegistry()
    if settings.telegram_enabled and settings.telegram_chat_id:
        client = TelegramClient(settings.telegram_bot_token or "", settings.telegram_api_base)
        registry.register(TelegramChannel(client, settings.telegram_chat_id))
    else:
        if settings.telegram_enabled:
            log.warning("TELEGRAM_CHAT_ID не задан — Telegram работает в режиме «лог вместо отправки»")
        else:
            log.warning("TELEGRAM_BOT_TOKEN не задан — режим «лог вместо отправки»")
        registry.register(LogTelegramChannel(settings.telegram_chat_id))
    if settings.smtp_host:
        registry.register(EmailChannel(settings, user_emails))
        log.info("Email-канал включён: %s:%s", settings.smtp_host, settings.smtp_port)
    if webhook_endpoints is not None:
        registry.register(
            WebhookChannel(webhook_endpoints, settings.webhook_allow_private, settings.webhook_timeout_seconds, now_iso=now_iso)
        )
    return registry
