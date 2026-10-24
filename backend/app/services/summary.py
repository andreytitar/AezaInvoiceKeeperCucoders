"""Итоги по валютам (без конвертации) и календарь оплат.

Итоги на дату D (`as_of`, по умолчанию сегодня):
- оплачено    — период оплачен и paid_date <= D;
- не оплачено — на дату D оплаты ещё не было;
- просрочено  — срок < D и на дату D не оплачено;
- предстоит   — срок >= D и на дату D не оплачено.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.domain.errors import ValidationError
from app.domain.money import Currency
from app.models import PaymentOccurrence
from app.repositories.payments import OccurrenceFilter, OccurrenceRepository

MAX_CALENDAR_DAYS = 92


@dataclass
class Bucket:
    amount: Decimal = Decimal("0.00")
    count: int = 0

    def add(self, amount: Decimal) -> None:
        self.amount += amount
        self.count += 1


@dataclass
class CurrencySummary:
    currency: Currency
    total: Bucket = field(default_factory=Bucket)
    paid: Bucket = field(default_factory=Bucket)
    unpaid: Bucket = field(default_factory=Bucket)
    overdue: Bucket = field(default_factory=Bucket)
    upcoming: Bucket = field(default_factory=Bucket)


@dataclass
class Summary:
    as_of: date
    currencies: list[CurrencySummary]


@dataclass
class CalendarDay:
    day: date
    occurrences: list[PaymentOccurrence]
    totals: list[CurrencySummary]


def paid_as_of(o: PaymentOccurrence, as_of: date) -> bool:
    return o.is_paid and o.paid_date is not None and o.paid_date <= as_of


def _accumulate(items, as_of: date) -> list[CurrencySummary]:
    by_cur = {c: CurrencySummary(c) for c in Currency}
    for o in items:
        s = by_cur[o.currency_snapshot]
        amount = o.amount_snapshot
        s.total.add(amount)
        if paid_as_of(o, as_of):
            s.paid.add(amount)
            continue
        s.unpaid.add(amount)
        if o.due_date < as_of:
            s.overdue.add(amount)
        else:
            s.upcoming.add(amount)
    return list(by_cur.values())


class SummaryService:
    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.occurrences = OccurrenceRepository(db)

    def summary(self, f: OccurrenceFilter | None = None, as_of: date | None = None) -> Summary:
        today = self.clock.today()
        as_of = as_of or today
        items = self.occurrences.all_filtered(f or OccurrenceFilter(), today)
        return Summary(as_of=as_of, currencies=_accumulate(items, as_of))

    def calendar(self, date_from: date, date_to: date, team_id: uuid.UUID | None = None) -> list[CalendarDay]:
        if date_to < date_from:
            raise ValidationError("Дата «по» раньше даты «с»", details={"field": "to"})
        if (date_to - date_from).days > MAX_CALENDAR_DAYS:
            raise ValidationError(f"Диапазон календаря не больше {MAX_CALENDAR_DAYS} дней", details={"field": "to"})
        today = self.clock.today()
        items = self.occurrences.all_filtered(
            OccurrenceFilter(date_from=date_from, date_to=date_to, team_id=team_id), today
        )
        by_day: dict[date, list[PaymentOccurrence]] = defaultdict(list)
        for o in sorted(items, key=lambda x: (x.due_date, x.title_snapshot)):
            by_day[o.due_date].append(o)
        return [
            CalendarDay(day=d, occurrences=occ, totals=[t for t in _accumulate(occ, today) if t.total.count])
            for d, occ in sorted(by_day.items())
        ]
