"""Webhook-канал: JSON с версией схемы, подпись HMAC-SHA256, ключ идемпотентности, таймауты.

Получатель (recipient) — id адреса из webhook_endpoints. Ретраи/дедупликацию делает общий диспетчер.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.infrastructure.channels.base import Notification, SendResult
from app.infrastructure.net_guard import UnsafeUrl, check_url

SCHEMA_VERSION = "1"
EVENTS = ("payment.reminder", "payment.paid", "payment.unpaid", "payment.overdue")


def event_name(kind: str) -> str:
    """kind доставки -> имя события: reminder -> payment.reminder, payment.paid:<id> -> payment.paid."""
    base = kind.split(":", 1)[0]
    return "payment.reminder" if base == "reminder" else base


@dataclass
class EndpointConfig:
    id: uuid.UUID
    url: str
    secret: str | None
    events: list[str]
    is_active: bool


def build_payload(n: Notification, event: str, idempotency_key: str, occurred_at: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "event": event,
        "event_id": idempotency_key,
        "occurred_at": occurred_at,
        "data": {
            "occurrence_id": str(n.occurrence_id),
            "recurring_payment_id": n.extra.get("recurring_payment_id"),
            "title": n.title,
            "amount": f"{n.amount:.2f}",
            "currency": n.currency,
            "due_date": n.due_date.isoformat(),
            "status": n.extra.get("status"),
            "paid_date": n.extra.get("paid_date"),
            "days_until_due": n.days_until_due,
        },
    }


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


async def post_signed(
    url: str,
    payload: dict,
    secret: str | None,
    event: str,
    idempotency_key: str,
    timeout: float,
    allow_private: bool,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SendResult:
    try:
        await asyncio.to_thread(check_url, url, allow_private)
    except UnsafeUrl as exc:
        return SendResult(ok=False, error=f"SSRF: {exc}", retryable=False)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ts = str(int(time.time()))  # unix-время подписи, не бизнес-дата
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "InvoiceKeeper-Webhook/1",
        "X-InvoiceKeeper-Event": event,
        "X-InvoiceKeeper-Delivery": idempotency_key,
        "Idempotency-Key": idempotency_key,
        "X-InvoiceKeeper-Timestamp": ts,
    }
    if secret:
        headers["X-InvoiceKeeper-Signature"] = sign(secret, ts, body)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
            resp = await client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        return SendResult(ok=False, error=f"webhook: {type(exc).__name__}")
    if 200 <= resp.status_code < 300:
        return SendResult(ok=True, external_id=f"HTTP {resp.status_code}")
    retryable = resp.status_code >= 500 or resp.status_code in (408, 429)
    return SendResult(ok=False, error=f"webhook: HTTP {resp.status_code}", retryable=retryable)


class WebhookChannel:
    name = "webhook"

    def __init__(
        self,
        endpoints: Callable[[], list[EndpointConfig]],
        allow_private: bool = False,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        now_iso: Callable[[], str] | None = None,
    ) -> None:
        self._endpoints = endpoints
        self.allow_private = allow_private
        self.timeout = timeout
        self.transport = transport
        self.now_iso = now_iso or (lambda: "")

    def recipients(self) -> list[str]:
        """Для напоминаний: активные адреса, подписанные на payment.reminder."""
        return [str(e.id) for e in self._endpoints() if e.is_active and "payment.reminder" in e.events]

    async def send(self, message: Notification, recipient: str) -> SendResult:
        ep = next((e for e in self._endpoints() if str(e.id) == recipient), None)
        if ep is None or not ep.is_active:
            return SendResult(ok=False, error="webhook endpoint removed or disabled", retryable=False)
        event = event_name(message.kind)
        key = message.extra.get("delivery_id") or str(uuid.uuid4())
        payload = build_payload(message, event, key, self.now_iso())
        return await post_signed(ep.url, payload, ep.secret, event, key, self.timeout, self.allow_private, self.transport)
