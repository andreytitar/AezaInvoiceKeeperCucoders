from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.domain.money import Currency
from app.domain.reminder_policy import days_until
from app.domain.schedule import Recurrence
from app.domain.status import PaymentStatus, compute_overdue
from app.models import PaymentOccurrence, RecurringPayment
from app.schemas.common import InputModel, OutputModel

Amount = Annotated[
    Decimal,
    Field(gt=0, max_digits=18, decimal_places=2, description="Сумма, не больше 2 знаков после запятой", examples=["55000.00"]),
]


def _money(v: Decimal) -> str:
    return f"{v:.2f}"


class RecurringPaymentCreate(InputModel):
    title: str = Field(min_length=1, max_length=200, examples=["Аренда офиса"])
    amount: Amount
    currency: Currency
    first_due_date: date = Field(description="Дата ближайшей оплаты; от её числа считаются следующие сроки")
    recurrence: Recurrence = Recurrence.MONTHLY


class RecurringPaymentOut(OutputModel):
    id: uuid.UUID
    title: str
    amount: str = Field(description="Строка Decimal, например \"55000.00\"", examples=["55000.00"])
    currency: Currency
    recurrence: Recurrence
    first_due_date: date
    anchor_day: int
    next_due_date: date | None = Field(description="Срок ближайшего неоплаченного периода")
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime


    @classmethod
    def build(cls, p: RecurringPayment, next_due: date | None) -> RecurringPaymentOut:
        return cls(
            id=p.id,
            title=p.title,
            amount=_money(p.amount),
            currency=p.currency,
            recurrence=p.recurrence,
            first_due_date=p.first_due_date,
            anchor_day=p.anchor_day,
            next_due_date=next_due,
            is_deleted=p.deleted_at is not None,
            deleted_at=p.deleted_at,
            created_at=p.created_at,
        )


class OccurrenceOut(OutputModel):
    id: uuid.UUID
    recurring_payment_id: uuid.UUID
    title: str
    amount: str = Field(description="Строка Decimal, например \"55000.00\"", examples=["55000.00"])
    currency: Currency
    due_date: date
    status: PaymentStatus
    paid_date: date | None
    is_overdue: bool = Field(description="Не оплачено после срока или оплачено позже срока")
    overdue_days: int
    days_until_due: int = Field(description="Дней до срока (отрицательное — срок прошёл)")
    recurring_payment_deleted: bool = Field(description="Платёж прекращён (история сохранена)")
    has_receipt: bool = Field(default=False, description="К периоду прикреплён чек или ссылка")


    @classmethod
    def build(cls, o: PaymentOccurrence, today: date) -> OccurrenceOut:
        info = compute_overdue(o.due_date, o.is_paid, o.paid_date, today)
        return cls(
            id=o.id,
            recurring_payment_id=o.recurring_payment_id,
            title=o.title_snapshot,
            amount=_money(o.amount_snapshot),
            currency=o.currency_snapshot,
            due_date=o.due_date,
            status=PaymentStatus.PAID if o.is_paid else PaymentStatus.UNPAID,
            paid_date=o.paid_date,
            is_overdue=info.is_overdue,
            overdue_days=info.overdue_days,
            days_until_due=days_until(o.due_date, today),
            recurring_payment_deleted=o.payment.deleted_at is not None,
            has_receipt=o.receipt is not None,
        )


class OccurrencePage(OutputModel):
    items: list[OccurrenceOut]
    total: int
    page: int
    page_size: int


class OccurrencePatch(InputModel):
    """Меняются только статус и фактическая дата оплаты. Дата — только вместе со статусом `paid`."""

    status: PaymentStatus
    paid_date: date | None = Field(default=None, description="По умолчанию — сегодня в APP_TIMEZONE; не в будущем")


OccurrenceSort = Literal[
    "due_date", "-due_date", "amount", "-amount", "title", "-title", "paid_date", "-paid_date", "currency", "-currency"
]


class MoneyBucket(OutputModel):
    amount: str = Field(examples=["55000.00"])
    count: int



class CurrencySummaryOut(OutputModel):
    currency: Currency
    total: MoneyBucket
    paid: MoneyBucket
    unpaid: MoneyBucket
    overdue: MoneyBucket = Field(description="На дату as_of не оплачено и срок прошёл")
    upcoming: MoneyBucket = Field(description="На дату as_of не оплачено и срок ещё не наступил")


class SummaryOut(OutputModel):
    as_of: date
    currencies: list[CurrencySummaryOut]


class CalendarDayOut(OutputModel):
    date: date
    occurrences: list[OccurrenceOut]
    totals: list[CurrencySummaryOut] = Field(description="Итоги дня по валютам (только валюты, которые есть в этот день)")


class CalendarOut(OutputModel):
    date_from: date = Field(alias="from")
    to: date
    today: date
    days: list[CalendarDayOut]

    model_config = {"populate_by_name": True, "from_attributes": True, "serialize_by_alias": True}
