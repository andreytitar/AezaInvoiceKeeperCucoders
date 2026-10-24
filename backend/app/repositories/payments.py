from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.domain.money import Currency
from app.models import PaymentOccurrence, RecurringPayment


class PaymentRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get(self, payment_id: uuid.UUID, include_deleted: bool = False) -> RecurringPayment | None:
        stmt = select(RecurringPayment).where(RecurringPayment.id == payment_id)
        if not include_deleted:
            stmt = stmt.where(RecurringPayment.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def list(self, include_deleted: bool = False) -> list[RecurringPayment]:
        stmt = select(RecurringPayment).order_by(RecurringPayment.created_at, RecurringPayment.title)
        if not include_deleted:
            stmt = stmt.where(RecurringPayment.deleted_at.is_(None))
        return list(self.db.scalars(stmt))

    def list_alive(self) -> list[RecurringPayment]:
        return self.list(include_deleted=False)

    def add(self, payment: RecurringPayment) -> RecurringPayment:
        self.db.add(payment)
        self.db.flush()
        return payment

    def find_by_title(self, title: str) -> RecurringPayment | None:
        return self.db.scalar(
            select(RecurringPayment).where(RecurringPayment.title == title, RecurringPayment.deleted_at.is_(None))
        )


@dataclass
class OccurrenceFilter:
    status: str | None = None  # paid | unpaid
    overdue: bool | None = None
    currency: Currency | None = None
    date_from: date | None = None
    date_to: date | None = None
    recurring_payment_id: uuid.UUID | None = None
    search: str | None = None


SORTS = {
    "due_date": (PaymentOccurrence.due_date,),
    "amount": (PaymentOccurrence.amount_snapshot,),
    "title": (PaymentOccurrence.title_snapshot,),
    "paid_date": (PaymentOccurrence.paid_date,),
    "currency": (PaymentOccurrence.currency_snapshot,),
}


def overdue_condition(today: date):
    """SQL-эквивалент domain.status.compute_overdue(...).is_overdue."""
    return or_(
        and_(PaymentOccurrence.is_paid.is_(False), PaymentOccurrence.due_date < today),
        and_(PaymentOccurrence.is_paid.is_(True), PaymentOccurrence.paid_date > PaymentOccurrence.due_date),
    )


class OccurrenceRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get(self, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
        return self.db.scalar(select(PaymentOccurrence).where(PaymentOccurrence.id == occurrence_id))

    def get_for_update(self, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
        return self.db.scalar(
            select(PaymentOccurrence)
            .where(PaymentOccurrence.id == occurrence_id)
            .with_for_update(of=PaymentOccurrence)
        )

    def list_for_payment(self, payment_id: uuid.UUID) -> list[PaymentOccurrence]:
        return list(
            self.db.scalars(
                select(PaymentOccurrence)
                .where(PaymentOccurrence.recurring_payment_id == payment_id)
                .order_by(PaymentOccurrence.due_date)
            )
        )

    def insert_if_absent(self, payment: RecurringPayment, due_date: date) -> bool:
        """Идемпотентная вставка периода со снимком названия, суммы и валюты."""
        stmt = (
            insert(PaymentOccurrence)
            .values(
                id=uuid.uuid4(),
                recurring_payment_id=payment.id,
                title_snapshot=payment.title,
                amount_snapshot=payment.amount,
                currency_snapshot=payment.currency,
                due_date=due_date,
                is_paid=False,
            )
            .on_conflict_do_nothing(constraint="uq_occurrence_payment_due")
            .returning(PaymentOccurrence.id)
        )
        return self.db.execute(stmt).first() is not None

    def next_unpaid_due(self, payment_ids: list[uuid.UUID]) -> dict[uuid.UUID, date | None]:
        rows = self.db.execute(
            select(PaymentOccurrence.recurring_payment_id, func.min(PaymentOccurrence.due_date))
            .where(PaymentOccurrence.recurring_payment_id.in_(payment_ids), PaymentOccurrence.is_paid.is_(False))
            .group_by(PaymentOccurrence.recurring_payment_id)
        ).all()
        found = {pid: d for pid, d in rows}
        return {pid: found.get(pid) for pid in payment_ids}

    def update_open_snapshots(self, payment: RecurringPayment, today: date) -> int:
        """Новые название/сумма/валюта — только для неоплаченных периодов со сроком сегодня и позже."""
        res = self.db.execute(
            update(PaymentOccurrence)
            .where(
                PaymentOccurrence.recurring_payment_id == payment.id,
                PaymentOccurrence.is_paid.is_(False),
                PaymentOccurrence.due_date >= today,
            )
            .values(
                title_snapshot=payment.title,
                amount_snapshot=payment.amount,
                currency_snapshot=payment.currency,
            )
            .execution_options(synchronize_session=False)
        )
        return res.rowcount or 0

    def delete_future_unpaid(self, payment_id: uuid.UUID, today: date) -> int:
        result = self.db.execute(
            delete(PaymentOccurrence).where(
                PaymentOccurrence.recurring_payment_id == payment_id,
                PaymentOccurrence.is_paid.is_(False),
                PaymentOccurrence.due_date > today,
            )
        )
        return result.rowcount or 0

    def _filtered(self, stmt: Select, f: OccurrenceFilter, today: date) -> Select:
        if f.status == "paid":
            stmt = stmt.where(PaymentOccurrence.is_paid.is_(True))
        elif f.status == "unpaid":
            stmt = stmt.where(PaymentOccurrence.is_paid.is_(False))
        if f.overdue is True:
            stmt = stmt.where(overdue_condition(today))
        elif f.overdue is False:
            stmt = stmt.where(~overdue_condition(today))
        if f.currency:
            stmt = stmt.where(PaymentOccurrence.currency_snapshot == f.currency)
        if f.date_from:
            stmt = stmt.where(PaymentOccurrence.due_date >= f.date_from)
        if f.date_to:
            stmt = stmt.where(PaymentOccurrence.due_date <= f.date_to)
        if f.recurring_payment_id:
            stmt = stmt.where(PaymentOccurrence.recurring_payment_id == f.recurring_payment_id)
        if f.search:
            pattern = f.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(PaymentOccurrence.title_snapshot.ilike(f"%{pattern}%", escape="\\"))
        return stmt

    def query(
        self, f: OccurrenceFilter, today: date, sort: str, offset: int, limit: int
    ) -> tuple[list[PaymentOccurrence], int]:
        base = self._filtered(select(PaymentOccurrence), f, today)
        total = self.db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
        desc = sort.startswith("-")
        cols = SORTS[sort.lstrip("-")]
        order = [c.desc().nulls_last() if desc else c.asc().nulls_last() for c in cols]
        order += [PaymentOccurrence.due_date.asc(), PaymentOccurrence.title_snapshot.asc(), PaymentOccurrence.id]
        items = list(self.db.scalars(base.order_by(*order).offset(offset).limit(limit)))
        return items, total

    def all_filtered(self, f: OccurrenceFilter, today: date) -> list[PaymentOccurrence]:
        return list(self.db.scalars(self._filtered(select(PaymentOccurrence), f, today)))
