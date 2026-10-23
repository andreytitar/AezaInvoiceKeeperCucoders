"""Telegram Bot API через httpx: таймауты, разбор ошибок. Ретраи делает диспетчер доставок."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.infrastructure.channels.base import Notification, SendResult
from app.infrastructure.channels.formatting import plain_text, telegram_html

log = logging.getLogger("app.telegram")


class TelegramError(Exception):
    def __init__(self, description: str, retryable: bool = True) -> None:
        super().__init__(description)
        self.retryable = retryable


class TelegramClient:
    def __init__(
        self,
        token: str,
        api_base: str = "https://api.telegram.org",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = f"{api_base.rstrip('/')}/bot{token}"
        self._timeout = timeout
        self._transport = transport

    async def call(self, method: str, payload: dict[str, Any], timeout: float | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=timeout or self._timeout, transport=self._transport) as client:
                resp = await client.post(f"{self._base}/{method}", json=payload)
        except httpx.HTTPError as exc:
            raise TelegramError(f"{method}: сетевая ошибка {type(exc).__name__}") from None
        try:
            data = resp.json()
        except ValueError:
            raise TelegramError(f"{method}: HTTP {resp.status_code}") from None
        if not data.get("ok"):
            desc = data.get("description", f"HTTP {resp.status_code}")
            # 4xx кроме 429 — ошибка запроса/настроек, повтор вряд ли поможет, но ретраи ограничены
            retryable = resp.status_code == 429 or resp.status_code >= 500
            raise TelegramError(f"{method}: {desc}", retryable=retryable)
        return data["result"]

    async def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self.call("sendMessage", payload)

    async def edit_message_text(self, chat_id: str | int, message_id: int, text: str, reply_markup: dict | None = None):
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        payload["reply_markup"] = reply_markup or {"inline_keyboard": []}
        return await self.call("editMessageText", payload)

    async def answer_callback_query(self, callback_query_id: str, text: str, show_alert: bool = False):
        return await self.call(
            "answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
        )

    async def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": json.dumps(["callback_query"])}
        if offset is not None:
            payload["offset"] = offset
        return await self.call("getUpdates", payload, timeout=timeout + 10)


def reply_markup_for(n: Notification) -> dict | None:
    if not n.actions:
        return None
    return {"inline_keyboard": [[{"text": a.text, "callback_data": a.callback_data} for a in n.actions]]}


class TelegramChannel:
    name = "telegram"

    def __init__(self, client: TelegramClient, chat_id: str) -> None:
        self.client = client
        self.chat_id = chat_id

    def recipients(self) -> list[str]:
        return [self.chat_id]

    async def send(self, message: Notification, recipient: str) -> SendResult:
        try:
            result = await self.client.send_message(recipient, telegram_html(message), reply_markup_for(message))
        except TelegramError as exc:
            return SendResult(ok=False, error=str(exc), retryable=exc.retryable)
        return SendResult(ok=True, external_id=f"{result['chat']['id']}:{result['message_id']}")


class LogTelegramChannel:
    """Режим «лог вместо отправки»: TELEGRAM_BOT_TOKEN не задан. Сообщение пишется в лог."""

    name = "telegram"

    def __init__(self, chat_id: str | None) -> None:
        self.chat_id = chat_id or "log"

    def recipients(self) -> list[str]:
        return [self.chat_id]

    async def send(self, message: Notification, recipient: str) -> SendResult:
        log.warning(
            "[DRY-RUN Telegram] TELEGRAM_BOT_TOKEN не задан, сообщение не отправлено. Получатель %s:\n%s",
            recipient,
            plain_text(message),
        )
        return SendResult(ok=True, external_id="dry-run")
