"""Периоды (occurrences): генерация, просмотр, отметка оплаты."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import NotFound
from app.domain.schedule import plan_due_dates
from app.domain.status import PaymentStatus, apply_status_change
from app.models import PaymentOccurrence, RecurringPayment, User
from app.repositories.deliveries import DeliveryRepository
from app.repositories.payments import OccurrenceFilter, OccurrenceRepository, PaymentRepository
from app.services.audit import AuditService, occurrence_snapshot
from app.services.webhooks import WebhookEvents


class OccurrenceGenerator:
    """Гарантирует существование периодов: вся история до сегодня, ближайший неоплаченный и следующий.
    Идемпотентно (UNIQUE(recurring_payment_id, due_date) + ON CONFLICT DO NOTHING)."""

    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.payments = PaymentRepository(db)
        self.occurrences = OccurrenceRepository(db)

    def ensure(self, payment: RecurringPayment, today: date | None = None) -> int:
        if payment.deleted_at is not None:
            return 0
        today = today or self.clock.today()
        existing = self.occurrences.list_for_payment(payment.id)
        paid = {o.due_date for o in existing if o.is_paid}
        have = {o.due_date for o in existing}
        created = 0
        for due in plan_due_dates(payment.recurrence, payment.first_due_date, payment.anchor_day, today, paid):
            if due not in have and self.occurrences.insert_if_absent(payment, due):
                created += 1
        return created

    def ensure_all(self) -> int:
        today = self.clock.today()
        created = 0
        for payment in self.payments.list_alive():
            created += self.ensure(payment, today)
            self.db.commit()
        return created


@dataclass
class OccurrencePage:
    items: list[PaymentOccurrence]
    total: int
    page: int
    page_size: int


class OccurrenceService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.occurrences = OccurrenceRepository(db)
        self.deliveries = DeliveryRepository(db)

    def list(self, f: OccurrenceFilter, sort: str, page: int, page_size: int) -> OccurrencePage:
        items, total = self.occurrences.query(f, self.clock.today(), sort, (page - 1) * page_size, page_size)
        return OccurrencePage(items, total, page, page_size)

    def get(self, occurrence_id: uuid.UUID) -> PaymentOccurrence:
        occ = self.occurrences.get(occurrence_id)
        if occ is None:
            raise NotFound("Период не найден")
        return occ

    def mark(
        self,
        occurrence_id: uuid.UUID,
        *,
        status: PaymentStatus,
        paid_date: date | None,
        paid_date_provided: bool,
        actor: User | None,
        actor_login: str | None = None,
    ) -> PaymentOccurrence:
        """Подтверждение/отмена оплаты конкретного периода (раздел 2.3). Идемпотентно."""
        occ = self.occurrences.get_for_update(occurrence_id)
        if occ is None:
            raise NotFound("Период не найден")
        mark = apply_status_change(
            current_is_paid=occ.is_paid,
            current_paid_date=occ.paid_date,
            new_status=status,
            paid_date=paid_date,
            paid_date_provided=paid_date_provided,
            today=self.clock.today(),
        )
        changed = (occ.is_paid, occ.paid_date) != (mark.is_paid, mark.paid_date)
        before = occurrence_snapshot(occ)
        was_paid = occ.is_paid
        occ.is_paid = mark.is_paid
        occ.paid_date = mark.paid_date
        if changed:
            occ.updated_by = actor.id if actor else None
            if mark.is_paid and was_paid:
                action = "occurrence.paid_date_changed"
            else:
                action = "occurrence.paid" if mark.is_paid else "occurrence.unpaid"
            AuditService(self.db, self.clock).log(
                action, entity_type="payment_occurrence", entity_id=occ.id, before=before,
                after=occurrence_snapshot(occ), actor=actor, actor_login=actor_login,
            )
            if was_paid != mark.is_paid:
                WebhookEvents(self.db, self.clock).emit(occ, "payment.paid" if mark.is_paid else "payment.unpaid")
        if mark.is_paid:
            self.deliveries.cancel_open_for_occurrence(occ.id)
        elif occ.payment.deleted_at is None:
            self.deliveries.reopen_cancelled_reminders(occ.id, self.clock.now())
        self.db.flush()
        OccurrenceGenerator(self.db, self.clock).ensure(occ.payment)
        self.db.commit()
        self.db.refresh(occ)
        return occ
