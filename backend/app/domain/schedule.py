"""Расчёт дат периодов регулярного платежа.

Каждая дата вычисляется от якоря (первой даты и anchor_day), а не от предыдущей даты:
31 янв -> 28/29 фев -> 31 мар. Если в месяце нет нужного числа, берётся последний день месяца.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from enum import StrEnum
from typing import Protocol


class Recurrence(StrEnum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def month_date(year: int, month: int, anchor_day: int) -> date:
    """Дата с числом anchor_day в указанном месяце (с переносом на последний день месяца)."""
    return date(year, month, min(anchor_day, days_in_month(year, month)))


def add_months(anchor: date, months: int, anchor_day: int | None = None) -> date:
    day = anchor_day if anchor_day is not None else anchor.day
    total = anchor.year * 12 + (anchor.month - 1) + months
    return month_date(total // 12, total % 12 + 1, day)


class RecurrenceStrategy(Protocol):
    def nth_due(self, anchor: date, anchor_day: int, index: int) -> date:
        """Срок периода с номером index (0 — первый период, anchor)."""
        ...

    def next_due(self, anchor: date, current: date) -> date:
        """Срок периода, следующего за current. Считается от якоря."""
        ...


class _MonthStepStrategy:
    def __init__(self, step_months: int) -> None:
        self.step = step_months

    def nth_due(self, anchor: date, anchor_day: int, index: int) -> date:
        return add_months(anchor, self.step * index, anchor_day)

    def next_due(self, anchor: date, current: date) -> date:
        months_from_anchor = (current.year - anchor.year) * 12 + (current.month - anchor.month)
        index = months_from_anchor // self.step + 1
        return self.nth_due(anchor, anchor.day, index)


class MonthlyStrategy(_MonthStepStrategy):
    def __init__(self) -> None:
        super().__init__(1)


class QuarterlyStrategy(_MonthStepStrategy):
    def __init__(self) -> None:
        super().__init__(3)


class YearlyStrategy(_MonthStepStrategy):
    def __init__(self) -> None:
        super().__init__(12)


class WeeklyStrategy:
    def nth_due(self, anchor: date, anchor_day: int, index: int) -> date:
        return anchor + timedelta(weeks=index)

    def next_due(self, anchor: date, current: date) -> date:
        index = (current - anchor).days // 7 + 1
        return self.nth_due(anchor, anchor.day, index)


STRATEGIES: dict[Recurrence, RecurrenceStrategy] = {
    Recurrence.MONTHLY: MonthlyStrategy(),
    Recurrence.WEEKLY: WeeklyStrategy(),
    Recurrence.QUARTERLY: QuarterlyStrategy(),
    Recurrence.YEARLY: YearlyStrategy(),
}


def strategy_for(recurrence: Recurrence | str) -> RecurrenceStrategy:
    return STRATEGIES[Recurrence(recurrence)]


def plan_due_dates(
    recurrence: Recurrence | str,
    anchor: date,
    anchor_day: int,
    today: date,
    paid_due_dates: set[date],
    max_items: int = 1000,
) -> list[date]:
    """Какие периоды должны существовать на дату today.

    Правило: все периоды со сроком <= today (история и просрочки), как минимум один будущий период,
    и периоды вперёд до тех пор, пока не появятся ближайший неоплаченный период и следующий за ним.
    paid_due_dates — сроки уже оплаченных периодов.
    """
    strategy = strategy_for(recurrence)
    result: list[date] = []
    first_unpaid_index: int | None = None
    for i in range(max_items):
        d = strategy.nth_due(anchor, anchor_day, i)
        has_future = bool(result) and result[-1] > today
        has_next_after_unpaid = first_unpaid_index is not None and len(result) - first_unpaid_index >= 2
        if has_future and has_next_after_unpaid:
            break
        result.append(d)
        if first_unpaid_index is None and d not in paid_due_dates:
            first_unpaid_index = len(result) - 1
    return result
