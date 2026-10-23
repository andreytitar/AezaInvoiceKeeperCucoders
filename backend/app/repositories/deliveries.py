from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.models import DeliveryStatus, NotificationDelivery, PaymentOccurrence

OPEN_STATUSES = (DeliveryStatus.PENDING, DeliveryStatus.FAILED, DeliveryStatus.SENDING)


class DeliveryRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def cancel_open_for_occurrence(self, occurrence_id: uuid.UUID, kinds: tuple[str, ...] = ("reminder",)) -> int:
        """Ещё не отправленные доставки периода -> cancelled (отметили оплату / удалили платёж)."""
        res = self.db.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.occurrence_id == occurrence_id,
                NotificationDelivery.kind.in_(kinds),
                NotificationDelivery.status.in_((DeliveryStatus.PENDING, DeliveryStatus.FAILED)),
            )
            .values(status=DeliveryStatus.CANCELLED, last_error="cancelled: paid or payment deleted")
        )
        return res.rowcount or 0

    def cancel_open_for_payment(self, payment_id: uuid.UUID) -> int:
        occ_ids = select(PaymentOccurrence.id).where(PaymentOccurrence.recurring_payment_id == payment_id)
        res = self.db.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.occurrence_id.in_(occ_ids),
                NotificationDelivery.status.in_((DeliveryStatus.PENDING, DeliveryStatus.FAILED)),
            )
            .values(status=DeliveryStatus.CANCELLED, last_error="cancelled: payment deleted")
            .execution_options(synchronize_session=False)
        )
        return res.rowcount or 0

    def reopen_cancelled_reminders(self, occurrence_id: uuid.UUID, now) -> int:
        """Оплату отменили до отправки напоминания: напоминание снова в очереди.
        Если напоминание уже было отправлено (sent), повтора нет."""
        res = self.db.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.occurrence_id == occurrence_id,
                NotificationDelivery.kind == "reminder",
                NotificationDelivery.status == DeliveryStatus.CANCELLED,
            )
            .values(status=DeliveryStatus.PENDING, next_attempt_at=now, attempts=0, last_error=None)
        )
        return res.rowcount or 0
