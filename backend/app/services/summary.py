"""Итоги по валютам: всего / оплачено / не оплачено / просрочено — сумма и количество, без конвертации."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.domain.money import Currency
from app.domain.status import compute_overdue
from app.repositories.payments import OccurrenceFilter, OccurrenceRepository


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


@dataclass
class Summary:
    as_of: date
    currencies: list[CurrencySummary]


class SummaryService:
    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.occurrences = OccurrenceRepository(db)

    def summary(self, f: OccurrenceFilter | None = None) -> Summary:
        today = self.clock.today()
        by_cur = {c: CurrencySummary(c) for c in Currency}
        for occ in self.occurrences.all_filtered(f or OccurrenceFilter(), today):
            s = by_cur[occ.currency_snapshot]
            amount = occ.amount_snapshot
            s.total.add(amount)
            if occ.is_paid:
                s.paid.add(amount)
            else:
                s.unpaid.add(amount)
                if compute_overdue(occ.due_date, False, None, today).is_overdue:
                    s.overdue.add(amount)
        return Summary(as_of=today, currencies=list(by_cur.values()))
