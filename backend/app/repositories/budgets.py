from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Budget, BudgetPeriod, PaymentOccurrence


class BudgetRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def list(self, period_type: BudgetPeriod | None, year: int | None, month: int | None) -> list[Budget]:
        stmt = select(Budget)
        if period_type:
            stmt = stmt.where(Budget.period_type == period_type)
        if year:
            stmt = stmt.where(Budget.year == year)
        if month:
            stmt = stmt.where(Budget.month == month)
        return list(self.db.scalars(stmt.order_by(Budget.year, Budget.month.nulls_first(), Budget.currency)))

    def find(self, period_type: BudgetPeriod, year: int, month: int | None, currency) -> Budget | None:
        stmt = select(Budget).where(
            Budget.period_type == period_type, Budget.year == year, Budget.currency == currency
        )
        stmt = stmt.where(Budget.month.is_(None)) if month is None else stmt.where(Budget.month == month)
        return self.db.scalar(stmt.with_for_update())

    def get(self, budget_id: uuid.UUID) -> Budget | None:
        return self.db.get(Budget, budget_id)

    def occurrences_due_between(self, start: date, end: date) -> list[PaymentOccurrence]:
        return list(
            self.db.scalars(
                select(PaymentOccurrence).where(PaymentOccurrence.due_date >= start, PaymentOccurrence.due_date <= end)
            )
        )
