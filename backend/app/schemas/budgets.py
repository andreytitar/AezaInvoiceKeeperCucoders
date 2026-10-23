from __future__ import annotations

import uuid
from datetime import date

from pydantic import Field

from app.domain.money import Currency
from app.models import BudgetPeriod
from app.schemas.common import InputModel, OutputModel
from app.schemas.payments import Amount


def _m(v) -> str | None:
    return None if v is None else f"{v:.2f}"


class BudgetUpsert(InputModel):
    period_type: BudgetPeriod
    year: int = Field(ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12, description="Обязателен для month, пусто для year")
    currency: Currency
    planned_amount: Amount


class BudgetOut(OutputModel):
    id: uuid.UUID
    period_type: BudgetPeriod
    year: int
    month: int | None
    currency: Currency
    planned_amount: str

    @classmethod
    def build(cls, b) -> BudgetOut:
        return cls(id=b.id, period_type=b.period_type, year=b.year, month=b.month, currency=b.currency,
                   planned_amount=_m(b.planned_amount))


class BudgetLineOut(OutputModel):
    currency: Currency
    budget: str | None = Field(description="Плановая сумма; null — бюджет не задан")
    scheduled: str = Field(description="Сумма периодов со сроком в периоде бюджета")
    paid: str
    unpaid: str
    remaining: str | None = Field(description="Остаток бюджета (бюджет − запланировано, не меньше 0)")
    overrun: str = Field(description="Превышение бюджета")
    is_over: bool
    usage_percent: float | None = Field(description="Запланировано / бюджет × 100")
    count: int


class BudgetReportOut(OutputModel):
    period_type: BudgetPeriod
    year: int
    month: int | None
    date_from: date
    date_to: date
    lines: list[BudgetLineOut]

    @classmethod
    def build(cls, r) -> BudgetReportOut:
        return cls(
            period_type=r.period_type, year=r.year, month=r.month, date_from=r.date_from, date_to=r.date_to,
            lines=[
                BudgetLineOut(
                    currency=line.currency, budget=_m(line.budget), scheduled=_m(line.scheduled), paid=_m(line.paid),
                    unpaid=_m(line.unpaid), remaining=_m(line.remaining), overrun=_m(line.overrun),
                    is_over=line.overrun > 0,
                    usage_percent=round(float(line.scheduled / line.budget * 100), 1) if line.budget else None,
                    count=line.count,
                )
                for line in r.lines
            ],
        )
