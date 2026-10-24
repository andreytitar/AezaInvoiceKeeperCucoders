import asyncio
from datetime import date, datetime, timezone

from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.telegram import TelegramChannel
from app.services.digest import send_weekly_digest
from tests.integration.helpers import create_payment
from tests.worker.test_telegram_button import FakeTelegramClient


def tg_container(container):
    client = FakeTelegramClient()
    container.channels = ChannelRegistry([TelegramChannel(client, "-100500")])
    return client


def at(clock, y, m, d, hour_msk):
    clock._now = datetime(y, m, d, hour_msk - 3, 0, tzinfo=timezone.utc)


def test_digest_monday_morning_once(admin, container, clock):
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-19")
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-28")
    client = tg_container(container)
    at(clock, 2026, 10, 26, 8)  # понедельник, 8:00 — рано
    assert asyncio.run(send_weekly_digest(container)) is False
    at(clock, 2026, 10, 26, 9)
    assert asyncio.run(send_weekly_digest(container)) is True
    assert asyncio.run(send_weekly_digest(container)) is False  # уже отправлено на этой неделе
    at(clock, 2026, 10, 27, 10)  # вторник
    assert asyncio.run(send_weekly_digest(container)) is False
    assert len(client.messages) == 1
    text = client.messages[0]["text"]
    assert "Сводка на неделю" in text and "Подписка" in text and "Сервер" in text
    at(clock, 2026, 11, 2, 9)  # следующий понедельник
    assert asyncio.run(send_weekly_digest(container)) is True


def test_digest_failure_retries(admin, container, clock):
    client = tg_container(container)

    async def boom(*a, **k):
        raise RuntimeError("telegram down")

    client.send_message = boom
    at(clock, 2026, 10, 26, 9)
    assert asyncio.run(send_weekly_digest(container)) is False
    ok = FakeTelegramClient()
    container.channels = ChannelRegistry([TelegramChannel(ok, "-100500")])
    assert asyncio.run(send_weekly_digest(container)) is True
    assert len(ok.messages) == 1


def test_manual_digest_endpoint(admin, user, container):
    client = tg_container(container)
    assert user.post("/api/v1/admin/send-digest").status_code == 403
    assert admin.post("/api/v1/admin/send-digest").json() == {"sent": True}
    assert len(client.messages) == 1


def test_digest_disabled(container, clock):
    container.settings.digest_weekday = -1
    tg_container(container)
    at(clock, 2026, 10, 26, 9)
    assert asyncio.run(send_weekly_digest(container)) is False
