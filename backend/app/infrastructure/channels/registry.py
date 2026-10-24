"""Сборка реестра каналов из конфигурации. Новый канал = класс с интерфейсом NotificationChannel
+ одна строка регистрации здесь."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.config import Settings
from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.chat_webhook import ChatWebhookChannel
from app.infrastructure.channels.email import EmailChannel
from app.infrastructure.channels.webhook import EndpointConfig, WebhookChannel
from app.infrastructure.channels.telegram import LogTelegramChannel, TelegramChannel, TelegramClient

log = logging.getLogger("app.channels")


def build_channels(
    settings: Settings,
    user_emails: Callable[[], list[str]] | None = None,
    webhook_endpoints: Callable[[], list[EndpointConfig]] | None = None,
    now_iso: Callable[[], str] | None = None,
    telegram_chat: Callable[[], str | None] | None = None,
) -> ChannelRegistry:
    """telegram_chat — чат для напоминаний: привязанный командой /bind или TELEGRAM_CHAT_ID."""
    registry = ChannelRegistry()
    chat = telegram_chat or (lambda: settings.telegram_chat_id)
    if settings.telegram_enabled:
        client = TelegramClient(settings.telegram_bot_token or "", settings.telegram_api_base)
        registry.register(TelegramChannel(client, chat))
        if not chat():
            log.warning("Чат для напоминаний не задан: привяжите группу командой /bind или задайте TELEGRAM_CHAT_ID")
    else:
        log.warning("TELEGRAM_BOT_TOKEN не задан — режим «лог вместо отправки»")
        registry.register(LogTelegramChannel(chat))
    if settings.smtp_host:
        registry.register(EmailChannel(settings, user_emails))
        log.info("Email-канал включён: %s:%s", settings.smtp_host, settings.smtp_port)
    if settings.chat_webhook_url:
        chat = ChatWebhookChannel(
            settings.chat_webhook_url, settings.chat_webhook_format, settings.webhook_allow_private,
            settings.webhook_timeout_seconds,
        )
        registry.register(chat)
        log.info("Чат-вебхук включён (формат %s)", chat.fmt)
    if webhook_endpoints is not None:
        registry.register(
            WebhookChannel(webhook_endpoints, settings.webhook_allow_private, settings.webhook_timeout_seconds, now_iso=now_iso)
        )
    return registry
