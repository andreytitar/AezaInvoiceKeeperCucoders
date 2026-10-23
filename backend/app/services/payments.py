"""Регулярные платежи: создание, список, прекращение (soft delete)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import NotFound, ValidationError
from app.domain.money import Currency
from app.domain.schedule import Recurrence
from app.infrastructure.channels.base import ChannelRegistry
from app.models import RecurringPayment, User
from app.repositories.deliveries import DeliveryRepository
from app.repositories.payments import OccurrenceRepository, PaymentRepository
from app.services.occurrences import OccurrenceGenerator
from app.services.audit import AuditService, payment_snapshot
from app.services.reminders import ReminderService


class PaymentService:
    def __init__(
        self, db: DbSession, clock: Clock, settings: Settings, channels: ChannelRegistry | None = None
    ) -> None:
        self.db = db
        self.channels = channels
        self.clock = clock
        self.settings = settings
        self.payments = PaymentRepository(db)
        self.occurrences = OccurrenceRepository(db)
        self.deliveries = DeliveryRepository(db)

    def list(self, include_deleted: bool = False) -> list[RecurringPayment]:
        return self.payments.list(include_deleted)

    def get(self, payment_id: uuid.UUID) -> RecurringPayment:
        p = self.payments.get(payment_id, include_deleted=True)
        if p is None:
            raise NotFound("Регулярный платёж не найден")
        return p

    def create(
        self,
        *,
        title: str,
        amount: Decimal,
        currency: Currency,
        first_due_date: date,
        recurrence: Recurrence = Recurrence.MONTHLY,
        actor: User | None,
    ) -> RecurringPayment:
        today = self.clock.today()
        if first_due_date < today - timedelta(days=366) or first_due_date > today + timedelta(days=5 * 366):
            raise ValidationError(
                "Дата ближайшей оплаты должна быть не раньше чем год назад и не позже чем через 5 лет",
                details={"field": "first_due_date"},
            )
        payment = self.payments.add(
            RecurringPayment(
                title=title,
                amount=amount,
                currency=currency,
                recurrence=recurrence,
                first_due_date=first_due_date,
                anchor_day=first_due_date.day,
                created_by=actor.id if actor else None,
            )
        )
        OccurrenceGenerator(self.db, self.clock).ensure(payment)
        self._after_create(payment)
        AuditService(self.db, self.clock).log(
            "payment.create", entity_type="recurring_payment", entity_id=payment.id, after=payment_snapshot(payment), actor=actor
        )
        self.db.commit()
        return payment

    def _after_create(self, payment: RecurringPayment) -> None:
        """Платёж добавлен позже чем за N дней до срока -> напоминание ставится в очередь сразу."""
        if self.channels is not None:
            ReminderService(self.db, self.clock, self.settings, self.channels).scan(payment.id, commit=False)

    def delete(self, payment_id: uuid.UUID, actor: User | None = None) -> RecurringPayment:
        """Прекращение: новые периоды не создаются, напоминаний больше нет, история сохраняется.
        Будущие неоплаченные периоды удаляются. Повторный DELETE -> 404."""
        payment = self.payments.get(payment_id)
        if payment is None:
            raise NotFound("Регулярный платёж не найден")
        before = payment_snapshot(payment)
        payment.deleted_at = self.clock.now()
        removed = self.occurrences.delete_future_unpaid(payment.id, self.clock.today())
        self.deliveries.cancel_open_for_payment(payment.id)
        AuditService(self.db, self.clock).log(
            "payment.delete",
            entity_type="recurring_payment",
            entity_id=payment.id,
            before=before,
            after={**payment_snapshot(payment), "future_unpaid_periods_removed": removed},
            actor=actor,
        )
        self.db.commit()
        return payment

    def next_due_dates(self, payment_ids: list[uuid.UUID]) -> dict[uuid.UUID, date | None]:
        return self.occurrences.next_unpaid_due(payment_ids)
