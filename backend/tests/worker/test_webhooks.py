"""Вебхуки: CRUD, SSRF, подпись HMAC, события, ретраи, без дублей, журнал доставок."""

import hashlib
import hmac
import json
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.webhook import WebhookChannel
from app.models import WebhookEndpoint
from app.services.webhooks import endpoint_configs
from tests.integration.helpers import create_payment, occurrences_of
from tests.worker.test_reminders import tick

ALL = ["payment.reminder", "payment.paid", "payment.unpaid", "payment.overdue"]


class Receiver:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.fail = 0

    def __call__(self, request: httpx.Request):
        if self.fail:
            self.fail -= 1
            return httpx.Response(503)
        self.requests.append(request)
        return httpx.Response(200)

    def events(self):
        return [json.loads(r.content)["event"] for r in self.requests]


@pytest.fixture
def receiver(container, fake_channel):
    container.settings.webhook_allow_private = True
    rec = Receiver()
    container.channels = ChannelRegistry(
        [
            fake_channel,
            WebhookChannel(
                endpoint_configs(container.session_factory, container.settings),
                allow_private=True,
                transport=httpx.MockTransport(rec),
                now_iso=lambda: container.clock.now().isoformat(),
            ),
        ]
    )
    return rec


def add_hook(admin, events=ALL, secret="s3cr3t-key"):
    r = admin.post("/api/v1/webhooks", json={"url": "http://hooks.internal/ik", "events": events, "secret": secret})
    assert r.status_code == 201, r.text
    return r.json()


def test_crud_secret_never_returned(admin, receiver, container):
    h = add_hook(admin)
    assert h["has_secret"] is True and "secret" not in h
    with container.session_factory() as db:
        stored = db.scalar(select(WebhookEndpoint.secret_enc))
        assert stored and "s3cr3t-key" not in stored  # хранится зашифрованным
    r = admin.patch(f"/api/v1/webhooks/{h['id']}", json={"is_active": False, "secret": None})
    assert r.json()["is_active"] is False and r.json()["has_secret"] is False
    assert len(admin.get("/api/v1/webhooks").json()) == 1
    assert admin.delete(f"/api/v1/webhooks/{h['id']}").status_code == 204
    assert admin.get(f"/api/v1/webhooks/{h['id']}/deliveries").status_code == 404


def test_validation_and_ssrf(admin, container):
    container.settings.webhook_allow_private = False
    for url in ("ftp://x.y/z", "http://127.0.0.1:8000/x", "http://localhost/x", "http://169.254.169.254/latest",
                "http://10.1.2.3/x", "http://[::1]/x", "http://user:pass@1.1.1.1/x"):
        r = admin.post("/api/v1/webhooks", json={"url": url, "events": ["payment.paid"]})
        assert r.status_code == 422, url
    assert admin.post("/api/v1/webhooks", json={"url": "http://1.1.1.1/x", "events": ["payment.bogus"]}).status_code == 422
    assert admin.post("/api/v1/webhooks", json={"url": "http://1.1.1.1/x", "events": []}).status_code == 422
    assert admin.post("/api/v1/webhooks", json={"url": "http://1.1.1.1/x", "events": ["payment.paid"]}).status_code == 201


def test_reminder_event_signed(admin, receiver):
    add_hook(admin)
    p = create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    assert receiver.events() == ["payment.reminder"]
    req = receiver.requests[0]
    body = json.loads(req.content)
    assert body["schema_version"] == "1" and body["data"]["title"] == "Сервер" and body["data"]["amount"] == "25.00"
    assert body["data"]["recurring_payment_id"] == p["id"] and body["event_id"] == req.headers["Idempotency-Key"]
    ts = req.headers["X-InvoiceKeeper-Timestamp"]
    expected = "sha256=" + hmac.new(b"s3cr3t-key", ts.encode() + b"." + req.content, hashlib.sha256).hexdigest()
    assert req.headers["X-InvoiceKeeper-Signature"] == expected
    assert req.headers["X-InvoiceKeeper-Event"] == "payment.reminder"


def test_paid_unpaid_events_each_change(admin, user, receiver):
    add_hook(admin, events=["payment.paid", "payment.unpaid"])
    p = create_payment(admin, first_due_date="2026-11-20")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    url = f"/api/v1/payment-occurrences/{oid}"
    user.patch(url, json={"status": "paid"})
    user.patch(url, json={"status": "paid", "paid_date": "2026-10-20"})  # смена даты — не новое событие
    user.patch(url, json={"status": "unpaid"})
    user.patch(url, json={"status": "paid"})
    assert receiver.events() == ["payment.paid", "payment.unpaid", "payment.paid"]
    keys = [r.headers["Idempotency-Key"] for r in receiver.requests]
    assert len(set(keys)) == 3
    paid = json.loads(receiver.requests[0].content)["data"]
    assert paid["status"] == "paid" and paid["paid_date"] == "2026-10-24"


def test_overdue_event_once(admin, receiver, container, clock):
    add_hook(admin, events=["payment.overdue"])
    create_payment(admin, first_due_date="2026-10-25")
    tick(container)
    assert receiver.events() == []
    clock.set_today(date(2026, 10, 26))
    tick(container)
    tick(container)
    clock.set_today(date(2026, 10, 30))
    tick(container)
    assert receiver.events() == ["payment.overdue"]


def test_retry_with_backoff_and_journal(admin, receiver, container, clock):
    h = add_hook(admin, events=["payment.reminder"])
    receiver.fail = 1
    create_payment(admin, first_due_date="2026-10-25")
    j = admin.get(f"/api/v1/webhooks/{h['id']}/deliveries").json()
    assert j["total"] == 1 and j["items"][0]["status"] == "failed" and "503" in j["items"][0]["last_error"]
    clock.advance(minutes=2)
    tick(container)
    tick(container)
    j = admin.get(f"/api/v1/webhooks/{h['id']}/deliveries").json()
    assert j["items"][0]["status"] == "sent" and j["items"][0]["attempts"] == 2 and j["items"][0]["event"] == "payment.reminder"
    assert len(receiver.requests) == 1


def test_inactive_endpoint_gets_nothing(admin, receiver):
    h = add_hook(admin)
    admin.patch(f"/api/v1/webhooks/{h['id']}", json={"is_active": False})
    create_payment(admin, first_due_date="2026-10-25")
    assert receiver.requests == []


def test_send_time_ssrf_check(admin, container, fake_channel):
    """Даже если адрес сохранили при WEBHOOK_ALLOW_PRIVATE=true, при выключенном флаге отправки нет."""
    container.settings.webhook_allow_private = True
    rec = Receiver()
    add_hook(admin, events=["payment.reminder"])
    container.settings.webhook_allow_private = False
    container.channels = ChannelRegistry(
        [WebhookChannel(endpoint_configs(container.session_factory, container.settings), allow_private=False,
                        transport=httpx.MockTransport(rec))]
    )
    create_payment(admin, first_due_date="2026-10-25")
    assert rec.requests == []


def test_ping(admin, container, monkeypatch):
    container.settings.webhook_allow_private = True
    h = add_hook(admin)
    seen = []

    async def fake_post(url, payload, secret, event, key, timeout, allow_private, transport=None):
        seen.append((url, payload["test"], secret))
        from app.infrastructure.channels.base import SendResult

        return SendResult(ok=True, external_id="HTTP 200")

    monkeypatch.setattr("app.services.webhooks.post_signed", fake_post)
    r = admin.post(f"/api/v1/webhooks/{h['id']}/test").json()
    assert r == {"ok": True, "detail": "HTTP 200"}
    assert seen == [("http://hooks.internal/ik", True, "s3cr3t-key")]
