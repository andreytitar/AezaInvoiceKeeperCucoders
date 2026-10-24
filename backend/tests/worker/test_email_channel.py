"""Email-канал с мок-SMTP: содержимое письма, получатели, тот же механизм доставки без дублей."""

import asyncio
import smtplib
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.infrastructure.channels.base import ChannelRegistry, Notification
from app.infrastructure.channels.email import EmailChannel, build_email
from app.models import DeliveryStatus, NotificationDelivery
from app.repositories.users import UserRepository
from tests.integration.helpers import create_payment
from tests.worker.test_reminders import tick


class FakeSMTP:
    sent: list = []
    fail_next = 0

    def __init__(self, settings):
        pass

    def send_message(self, msg):
        if FakeSMTP.fail_next:
            FakeSMTP.fail_next -= 1
            raise smtplib.SMTPServerDisconnected("boom")
        FakeSMTP.sent.append(msg)

    def quit(self):
        pass


def email_channel(container):
    FakeSMTP.sent = []
    FakeSMTP.fail_next = 0
    container.settings.smtp_host = "smtp.test"
    container.settings.email_recipients = "team@example.com, Team@example.com"

    def user_emails():
        with container.session_factory() as db:
            return UserRepository(db).active_emails()

    return EmailChannel(container.settings, user_emails, smtp_factory=FakeSMTP)


def test_email_content():
    n = Notification(uuid.uuid4(), "Аренда <офиса>", Decimal("55000"), "RUB", date(2026, 10, 26), days_until_due=2)
    msg = build_email(n, "IK <ik@x.y>", "a@b.cd")
    assert "Аренда <офиса>" in msg["Subject"] and "26.10.2026" in msg["Subject"]
    text = msg.get_body(("plain",)).get_content()
    assert "55\u00a0000,00\u00a0₽" in text and "RUB" in text and "26.10.2026" in text
    assert "55 000" not in text
    assert "&lt;офиса&gt;" in msg.get_body(("html",)).get_content()


def test_reminder_sent_by_email_to_static_and_user_recipients(admin, container, fake_channel):
    admin.post("/api/v1/users", json={"login": "petr", "password": "secret1", "email": "petr@example.com"})
    container.channels = ChannelRegistry([fake_channel, email_channel(container)])
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    tick(container)
    tick(container)
    to = sorted(m["To"] for m in FakeSMTP.sent)
    assert to == ["petr@example.com", "team@example.com"]  # дубли адресов схлопнуты, повторный тик не шлёт
    assert len(fake_channel.sent) == 1
    with container.session_factory() as db:
        rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.channel == "email")).all()
        assert {r.status for r in rows} == {DeliveryStatus.SENT}


def test_smtp_failure_retries_without_duplicates(admin, container, clock):
    ch = email_channel(container)
    container.settings.email_to_users = False
    FakeSMTP.fail_next = 1
    container.channels = ChannelRegistry([ch])
    create_payment(admin, first_due_date="2026-10-25")
    assert FakeSMTP.sent == []
    clock.advance(minutes=2)
    tick(container)
    tick(container)
    assert len(FakeSMTP.sent) == 1


def test_email_disabled_without_host(container):
    from app.infrastructure.channels.registry import build_channels

    container.settings.smtp_host = None
    assert "email" not in build_channels(container.settings).names()
    container.settings.smtp_host = "mailpit"
    assert "email" in build_channels(container.settings).names()


def test_send_handles_connection_error(container):
    container.settings.smtp_host = "127.0.0.1"
    container.settings.smtp_port = 1  # закрытый порт
    container.settings.smtp_security = "none"
    container.settings.smtp_timeout_seconds = 2
    ch = EmailChannel(container.settings)
    n = Notification(uuid.uuid4(), "X", Decimal("1"), "EUR", date(2026, 10, 26))
    r = asyncio.run(ch.send(n, "a@b.cd"))
    assert not r.ok and "SMTP" in r.error
