from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.models import DeliveryStatus, NotificationDelivery, PaymentOccurrence, RecurringPayment


class ReminderRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def candidates(
        self, window_end: date, payment_id: uuid.UUID | None = None, team_id: uuid.UUID | None = None
    ) -> list[PaymentOccurrence]:
        """Неоплаченные периоды живых платежей со сроком <= window_end (включая просроченные)."""
        stmt = (
            select(PaymentOccurrence)
            .join(RecurringPayment, RecurringPayment.id == PaymentOccurrence.recurring_payment_id)
            .where(
                PaymentOccurrence.is_paid.is_(False),
                RecurringPayment.deleted_at.is_(None),
                PaymentOccurrence.due_date <= window_end,
            )
        )
        if payment_id:
            stmt = stmt.where(PaymentOccurrence.recurring_payment_id == payment_id)
        if team_id is not None:
            stmt = stmt.where(RecurringPayment.team_id == team_id)
        return list(self.db.scalars(stmt))

    def enqueue(self, occurrence_id: uuid.UUID, channel: str, recipient: str, kind: str, now: datetime) -> bool:
        """INSERT ... ON CONFLICT DO NOTHING: повторная проверка не создаёт дубль."""
        stmt = (
            insert(NotificationDelivery)
            .values(
                id=uuid.uuid4(),
                occurrence_id=occurrence_id,
                channel=channel,
                recipient=recipient,
                kind=kind,
                status=DeliveryStatus.PENDING,
                attempts=0,
                next_attempt_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_delivery_dedup")
            .returning(NotificationDelivery.id)
        )
        return self.db.execute(stmt).first() is not None

    def reminder_sent_before(self, occurrence_id: uuid.UUID, channel: str, recipient: str, before: datetime) -> bool:
        return (
            self.db.scalar(
                select(NotificationDelivery.id).where(
                    NotificationDelivery.occurrence_id == occurrence_id,
                    NotificationDelivery.channel == channel,
                    NotificationDelivery.recipient == recipient,
                    NotificationDelivery.kind == "reminder",
                    NotificationDelivery.status == DeliveryStatus.SENT,
                    NotificationDelivery.sent_at < before,
                )
            )
            is not None
        )

    def claim_batch(self, now: datetime, limit: int) -> list[NotificationDelivery]:
        """Атомарный захват: pending/failed с наступившим next_attempt_at -> sending.
        SKIP LOCKED позволяет нескольким worker'ам работать параллельно без дублей."""
        ids = (
            select(NotificationDelivery.id)
            .where(
                NotificationDelivery.status.in_((DeliveryStatus.PENDING, DeliveryStatus.FAILED)),
                NotificationDelivery.next_attempt_at <= now,
            )
            .order_by(NotificationDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        stmt = (
            update(NotificationDelivery)
            .where(NotificationDelivery.id.in_(ids))
            .values(status=DeliveryStatus.SENDING, locked_at=now, attempts=NotificationDelivery.attempts + 1)
            .returning(NotificationDelivery)
            .execution_options(synchronize_session=False)
        )
        return list(self.db.scalars(stmt))

    def release_stale(self, older_than: datetime) -> int:
        """Зависшие в sending (worker упал посреди отправки) возвращаются в pending."""
        res = self.db.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.status == DeliveryStatus.SENDING, NotificationDelivery.locked_at < older_than)
            .values(status=DeliveryStatus.PENDING, locked_at=None, next_attempt_at=older_than)
        )
        return res.rowcount or 0

    def get(self, delivery_id: uuid.UUID) -> NotificationDelivery | None:
        return self.db.get(NotificationDelivery, delivery_id)

    def list_for_occurrence(self, occurrence_id: uuid.UUID) -> list[NotificationDelivery]:
        return list(
            self.db.scalars(select(NotificationDelivery).where(NotificationDelivery.occurrence_id == occurrence_id))
        )
