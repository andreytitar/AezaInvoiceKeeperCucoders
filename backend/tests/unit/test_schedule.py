from datetime import date

import pytest

from app.domain.schedule import (
    MonthlyStrategy,
    Recurrence,
    add_months,
    plan_due_dates,
)


def monthly_dates(anchor: date, n: int) -> list[date]:
    s = MonthlyStrategy()
    return [s.nth_due(anchor, anchor.day, i) for i in range(n)]


def test_anchor_31_clamps_to_month_end_and_returns_to_31():
    assert monthly_dates(date(2026, 1, 31), 4) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_leap_year_february_29():
    assert monthly_dates(date(2028, 1, 31), 3) == [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)]
    assert monthly_dates(date(2028, 1, 30), 3)[1] == date(2028, 2, 29)


def test_anchor_30_february_non_leap():
    assert monthly_dates(date(2027, 1, 30), 3) == [date(2027, 1, 30), date(2027, 2, 28), date(2027, 3, 30)]


def test_dates_computed_from_anchor_not_from_previous_date():
    # если считать от предыдущей даты, после февраля получилось бы 28 марта
    s = MonthlyStrategy()
    assert s.next_due(date(2026, 1, 31), date(2026, 2, 28)) == date(2026, 3, 31)


def test_year_rollover():
    assert monthly_dates(date(2026, 11, 15), 3) == [date(2026, 11, 15), date(2026, 12, 15), date(2027, 1, 15)]


def test_add_months_negative():
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


@pytest.mark.parametrize(
    "current, expected",
    [
        (date(2026, 1, 31), date(2026, 2, 28)),
        (date(2026, 2, 28), date(2026, 3, 31)),
        (date(2026, 12, 31), date(2027, 1, 31)),
    ],
)
def test_next_due_from_anchor(current, expected):
    assert MonthlyStrategy().next_due(date(2026, 1, 31), current) == expected


def test_plan_future_payment_has_first_and_next():
    plan = plan_due_dates(Recurrence.MONTHLY, date(2026, 11, 1), 1, date(2026, 10, 24), set())
    assert plan == [date(2026, 11, 1), date(2026, 12, 1)]


def test_plan_includes_all_past_periods_and_at_least_one_future():
    # просрочка не останавливает создание следующих периодов
    plan = plan_due_dates(Recurrence.MONTHLY, date(2026, 8, 25), 25, date(2026, 10, 24), set())
    assert plan == [date(2026, 8, 25), date(2026, 9, 25), date(2026, 10, 25)]


def test_plan_when_current_paid_creates_one_more():
    paid = {date(2026, 10, 25)}
    plan = plan_due_dates(Recurrence.MONTHLY, date(2026, 10, 25), 25, date(2026, 10, 24), paid)
    assert plan == [date(2026, 10, 25), date(2026, 11, 25), date(2026, 12, 25)]


def test_plan_due_today_is_not_future():
    plan = plan_due_dates(Recurrence.MONTHLY, date(2026, 10, 24), 24, date(2026, 10, 24), set())
    assert plan == [date(2026, 10, 24), date(2026, 11, 24)]
