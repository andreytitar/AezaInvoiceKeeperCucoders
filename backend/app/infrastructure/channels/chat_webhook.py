"""Канал «чат-вебхук»: Slack / Discord / Mattermost incoming webhook.

Пример того, как добавить свой канал: класс с атрибутом `name`, методами `recipients()` и
`async send(message, recipient) -> SendResult`, плюс регистрация в `build_channels()`.
Ядро рассылки (очередь, дедупликация, ретраи) при этом не меняется.
"""

from __future__ import annotations

import asyncio
import hashlib
from urllib.parse import urlsplit

import httpx

from app.domain.money import format_amount
from app.infrastructure.channels.base import Notification, SendResult
from app.infrastructure.channels.formatting import due_phrase
from app.infrastructure.net_guard import UnsafeUrl, check_url


def detect_format(url: str, configured: str) -> str:
    if configured != "auto":
        return configured
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("discord.com") or host.endswith("discordapp.com"):
        return "discord"
    if host.endswith("slack.com"):
        return "slack"
    return "mattermost"  # Mattermost принимает Slack-совместимый {"text": ...}


def render(n: Notification, fmt: str) -> dict:
    head = "Просроченный платёж" if n.days_until_due < 0 else "Напоминание об оплате"
    amount = f"{format_amount(n.amount, n.currency)} ({n.currency})"
    due = f"{n.due_date:%d.%m.%Y} — {due_phrase(n.days_until_due)}"
    if fmt == "discord":
        return {
            "username": "Invoice Keeper",
            "content": f"**{head}**\n**{n.title}**\nСумма: **{amount}**\nДата оплаты: **{due}**",
            "allowed_mentions": {"parse": []},
        }
    # Slack mrkdwn и Mattermost
    return {"username": "Invoice Keeper", "text": f"*{head}*\n*{n.title}*\nСумма: *{amount}*\nДата оплаты: *{due}*"}


class ChatWebhookChannel:
    name = "chat"

    def __init__(
        self,
        url: str,
        fmt: str = "auto",
        allow_private: bool = False,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url
        self.fmt = detect_format(url, fmt)
        self.allow_private = allow_private
        self.timeout = timeout
        self.transport = transport
        # в БД хранится не URL (в нём секретный токен), а его отпечаток
        self._recipient = f"{self.fmt}:{hashlib.sha256(url.encode()).hexdigest()[:12]}"

    def recipients(self) -> list[str]:
        return [self._recipient]

    async def send(self, message: Notification, recipient: str) -> SendResult:
        try:
            await asyncio.to_thread(check_url, self.url, self.allow_private)
        except UnsafeUrl as exc:
            return SendResult(ok=False, error=f"SSRF: {exc}", retryable=False)
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, transport=self.transport) as c:
                resp = await c.post(self.url, json=render(message, self.fmt))
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"chat webhook: {type(exc).__name__}")
        if 200 <= resp.status_code < 300:
            return SendResult(ok=True, external_id=f"HTTP {resp.status_code}")
        return SendResult(
            ok=False,
            error=f"chat webhook: HTTP {resp.status_code}",
            retryable=resp.status_code >= 500 or resp.status_code == 429,
        )
