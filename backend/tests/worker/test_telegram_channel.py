import asyncio
import json
import uuid
from datetime import date
from decimal import Decimal

import httpx

from app.infrastructure.channels.base import Notification
from app.infrastructure.channels.telegram import LogTelegramChannel, TelegramChannel, TelegramClient
from app.infrastructure.logging import mask_secrets

MSG = Notification(
    occurrence_id=uuid.uuid4(),
    title="Аренда <офиса>",
    amount=Decimal("55000.00"),
    currency="RUB",
    due_date=date(2026, 10, 26),
    days_until_due=2,
)


def channel(handler):
    client = TelegramClient("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef123", transport=httpx.MockTransport(handler))
    return TelegramChannel(client, "-100500")


def test_send_message_contains_required_fields():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7, "chat": {"id": -100500}}})

    result = asyncio.run(channel(handler).send(MSG, "-100500"))
    assert result.ok and result.external_id == "-100500:7"
    assert seen["url"].endswith("/sendMessage")
    text = seen["body"]["text"]
    assert "Аренда &lt;офиса&gt;" in text and "55 000,00 ₽" in text and "RUB" in text and "26.10.2026" in text
    assert seen["body"]["chat_id"] == "-100500" and seen["body"]["parse_mode"] == "HTML"


def test_server_error_is_retryable_and_bad_request_is_not():
    r500 = asyncio.run(channel(lambda r: httpx.Response(502, json={"ok": False, "description": "Bad Gateway"})).send(MSG, "1"))
    assert not r500.ok and r500.retryable
    r400 = asyncio.run(
        channel(lambda r: httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})).send(MSG, "1")
    )
    assert not r400.ok and not r400.retryable and "chat not found" in r400.error


def test_network_error_does_not_leak_token():
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    r = asyncio.run(channel(handler).send(MSG, "1"))
    assert not r.ok and "ABCDEFGHIJ" not in r.error


def test_log_channel_dry_run(caplog):
    r = asyncio.run(LogTelegramChannel("-1").send(MSG, "-1"))
    assert r.ok and r.external_id == "dry-run"
    assert "DRY-RUN" in caplog.text


def test_mask_secrets():
    s = mask_secrets("GET https://api.telegram.org/bot123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef123/sendMessage password=hunter2")
    assert "ABCDEFGH" not in s and "hunter2" not in s
