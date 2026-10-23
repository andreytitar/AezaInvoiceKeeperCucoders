"""Сборка реестра каналов из конфигурации."""

from __future__ import annotations

import logging

from app.config import Settings
from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.telegram import LogTelegramChannel, TelegramChannel, TelegramClient

log = logging.getLogger("app.channels")


def build_channels(settings: Settings) -> ChannelRegistry:
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
    return registry
