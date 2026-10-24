"""Бюджеты на месяц/год и отчёт «план/факт» по каждой валюте (без конвертации).

Запланировано — сумма периодов со сроком в периоде бюджета; оплачено — из них оплаченные;
остаток = бюджет − запланировано (не меньше 0); превышение = запланировано − бюджет (если больше 0).
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.domain.errors import NotFound, ValidationError
from app.domain.money import Currency
from app.models import Budget, BudgetPeriod, User
from app.repositories.budgets import BudgetRepository
from app.services.audit import AuditService

ZERO = Decimal("0.00")


def period_bounds(period_type: BudgetPeriod, year: int, month: int | None) -> tuple[date, date]:
    if period_type == BudgetPeriod.MONTH:
        if not month or not 1 <= month <= 12:
            raise ValidationError("Для месячного бюджета нужен месяц 1–12", details={"field": "month"})
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if month is not None:
        raise ValidationError("Для годового бюджета месяц не указывается", details={"field": "month"})
    return date(year, 1, 1), date(year, 12, 31)


@dataclass
class BudgetLine:
    currency: Currency
    budget: Decimal | None
    scheduled: Decimal
    paid: Decimal
    unpaid: Decimal
    remaining: Decimal | None
    overrun: Decimal
    count: int


@dataclass
class BudgetReport:
    period_type: BudgetPeriod
    year: int
    month: int | None
    date_from: date
    date_to: date
    lines: list[BudgetLine]


def _snap(b: Budget) -> dict:
    return {"period_type": b.period_type, "year": b.year, "month": b.month, "currency": b.currency, "planned_amount": b.planned_amount}


class BudgetService:
    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.repo = BudgetRepository(db)

    def list(self, period_type=None, year=None, month=None, team_id=None) -> list[Budget]:
        return self.repo.list(period_type, year, month, team_id=team_id)

    def upsert(self, *, period_type: BudgetPeriod, year: int, month: int | None, currency: Currency,
               planned_amount: Decimal, actor: User | None) -> tuple[Budget, bool]:
        period_bounds(period_type, year, month)
        team_id = actor.team_id if actor is not None else None
        b = self.repo.find(period_type, year, month, currency, team_id=team_id)
        created = b is None
        before = None if created else _snap(b)
        if created:
            b = Budget(
                team_id=team_id,
                period_type=period_type,
                year=year,
                month=month,
                currency=currency,
                planned_amount=planned_amount,
            )
            self.db.add(b)
        else:
            b.planned_amount = planned_amount
        self.db.flush()
        AuditService(self.db, self.clock).log(
            "budget.create" if created else "budget.update", entity_type="budget", entity_id=b.id,
            before=before, after=_snap(b), actor=actor,
        )
        self.db.commit()
        return b, created

    def delete(self, budget_id: uuid.UUID, actor: User | None) -> None:
        b = self.repo.get(budget_id)
        if b is None or (actor is not None and b.team_id != actor.team_id):
            raise NotFound("Бюджет не найден")
        AuditService(self.db, self.clock).log("budget.delete", entity_type="budget", entity_id=b.id, before=_snap(b), actor=actor)
        self.db.delete(b)
        self.db.commit()

    def report(self, period_type: BudgetPeriod, year: int, month: int | None, team_id: uuid.UUID | None = None) -> BudgetReport:
        start, end = period_bounds(period_type, year, month)
        budgets = {
            b.currency: b.planned_amount
            for b in self.repo.list(period_type, year, month, team_id=team_id)
            if b.month == month
        }
        lines = []
        occ = self.repo.occurrences_due_between(start, end, team_id=team_id)
        for cur in Currency:
            items = [o for o in occ if o.currency_snapshot == cur]
            scheduled = sum((o.amount_snapshot for o in items), ZERO)
            paid = sum((o.amount_snapshot for o in items if o.is_paid), ZERO)
            budget = budgets.get(cur)
            lines.append(
                BudgetLine(
                    currency=cur,
                    budget=budget,
                    scheduled=scheduled,
                    paid=paid,
                    unpaid=scheduled - paid,
                    remaining=max(budget - scheduled, ZERO) if budget is not None else None,
                    overrun=max(scheduled - budget, ZERO) if budget is not None else ZERO,
                    count=len(items),
                )
            )
        return BudgetReport(period_type, year, month, start, end, lines)
