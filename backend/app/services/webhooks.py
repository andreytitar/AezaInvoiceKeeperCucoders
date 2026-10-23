"""Вебхуки: управление адресами (admin) и постановка событий в общую очередь доставок."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import NotFound, ValidationError
from app.infrastructure.channels.base import Notification, SendResult
from app.infrastructure.channels.webhook import EVENTS, EndpointConfig, build_payload, post_signed
from app.infrastructure.net_guard import UnsafeUrl, check_url
from app.infrastructure.secrets_box import SecretBox
from app.models import PaymentOccurrence, User, WebhookEndpoint
from app.repositories.reminders import ReminderRepository
from app.repositories.webhooks import WebhookRepository
from app.services.audit import AuditService


def _snap(ep: WebhookEndpoint) -> dict:
    return {
        "url": ep.url,
        "events": list(ep.events),
        "is_active": ep.is_active,
        "description": ep.description,
        "has_secret": ep.secret_enc is not None,
    }


def endpoint_configs(session_factory, settings: Settings):
    """Провайдер адресов для WebhookChannel (читает БД при каждом вызове)."""
    box = SecretBox(settings.secret_key)

    def provider() -> list[EndpointConfig]:
        with session_factory() as db:
            return [
                EndpointConfig(
                    id=e.id,
                    url=e.url,
                    secret=box.decrypt(e.secret_enc) if e.secret_enc else None,
                    events=list(e.events),
                    is_active=e.is_active,
                )
                for e in WebhookRepository(db).list()
            ]

    return provider


class WebhookService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.repo = WebhookRepository(db)
        self.box = SecretBox(settings.secret_key)

    def _validate(self, url: str, events: list[str]) -> None:
        try:
            check_url(url, self.settings.webhook_allow_private)
        except UnsafeUrl as exc:
            raise ValidationError(str(exc), details={"field": "url"}) from None
        bad = [e for e in events if e not in EVENTS]
        if bad or not events:
            raise ValidationError(f"События: {', '.join(EVENTS)}", details={"field": "events", "invalid": bad})

    def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        ep = self.repo.get(endpoint_id)
        if ep is None:
            raise NotFound("Вебхук не найден")
        return ep

    def list(self) -> list[WebhookEndpoint]:
        return self.repo.list()

    def create(self, *, url: str, events: list[str], secret: str | None, is_active: bool, description: str | None,
               actor: User | None) -> WebhookEndpoint:
        events = sorted(set(events))
        self._validate(url, events)
        ep = self.repo.add(
            WebhookEndpoint(
                url=url,
                events=events,
                is_active=is_active,
                description=description,
                secret_enc=self.box.encrypt(secret) if secret else None,
            )
        )
        AuditService(self.db, self.clock).log("webhook.create", entity_type="webhook", entity_id=ep.id, after=_snap(ep), actor=actor)
        self.db.commit()
        return ep

    def update(self, endpoint_id: uuid.UUID, fields: dict, actor: User | None) -> WebhookEndpoint:
        ep = self.get(endpoint_id)
        before = _snap(ep)
        url = fields.get("url", ep.url)
        events = sorted(set(fields.get("events", ep.events)))
        self._validate(url, events)
        ep.url, ep.events = url, events
        if "is_active" in fields:
            ep.is_active = bool(fields["is_active"])
        if "description" in fields:
            ep.description = fields["description"]
        if "secret" in fields:
            ep.secret_enc = self.box.encrypt(fields["secret"]) if fields["secret"] else None
        AuditService(self.db, self.clock).log(
            "webhook.update", entity_type="webhook", entity_id=ep.id, before=before, after=_snap(ep), actor=actor
        )
        self.db.commit()
        return ep

    def delete(self, endpoint_id: uuid.UUID, actor: User | None) -> None:
        ep = self.get(endpoint_id)
        AuditService(self.db, self.clock).log("webhook.delete", entity_type="webhook", entity_id=ep.id, before=_snap(ep), actor=actor)
        self.db.delete(ep)
        self.db.commit()

    def deliveries(self, endpoint_id: uuid.UUID, page: int, page_size: int):
        self.get(endpoint_id)
        return self.repo.deliveries(endpoint_id, (page - 1) * page_size, page_size)

    async def ping(self, endpoint_id: uuid.UUID) -> SendResult:
        """Тестовое событие payment.reminder с вымышленными данными (не пишется в очередь)."""
        ep = self.get(endpoint_id)
        n = Notification(
            occurrence_id=uuid.UUID(int=0),
            title="Тестовое событие Invoice Keeper",
            amount=Decimal("1.00"),
            currency="RUB",
            due_date=self.clock.today(),
            kind="reminder",
            extra={"status": "unpaid", "paid_date": None, "recurring_payment_id": None},
        )
        key = f"ping-{uuid.uuid4()}"
        payload = build_payload(n, "payment.reminder", key, self.clock.now().isoformat())
        payload["test"] = True
        secret = self.box.decrypt(ep.secret_enc) if ep.secret_enc else None
        return await post_signed(
            ep.url, payload, secret, "payment.reminder", key, self.settings.webhook_timeout_seconds,
            self.settings.webhook_allow_private,
        )


class WebhookEvents:
    """Постановка событий payment.paid / payment.unpaid / payment.overdue в notification_deliveries."""

    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.repo = WebhookRepository(db)
        self.deliveries = ReminderRepository(db)

    def emit(self, occ: PaymentOccurrence, event: str) -> int:
        """Каждое изменение статуса — отдельное событие со своим ключом идемпотентности."""
        kind = f"{event}:{uuid.uuid4().hex[:12]}"
        created = 0
        for ep in self.repo.subscribed(event):
            if self.deliveries.enqueue(occ.id, "webhook", str(ep.id), kind, self.clock.now()):
                created += 1
        return created

    def scan_overdue(self) -> int:
        """Одно событие payment.overdue на период и адрес (UNIQUE), когда срок прошёл и не оплачено."""
        endpoints = self.repo.subscribed("payment.overdue")
        if not endpoints:
            return 0
        today = self.clock.today()
        created = 0
        for occ in self.deliveries.candidates(today - timedelta(days=1)):
            for ep in endpoints:
                if self.deliveries.enqueue(occ.id, "webhook", str(ep.id), "payment.overdue", self.clock.now()):
                    created += 1
        self.db.commit()
        return created
