from datetime import date

from app.domain.schedule import Recurrence, plan_due_dates, strategy_for


def nth(rec, anchor, n):
    s = strategy_for(rec)
    return [s.nth_due(anchor, anchor.day, i) for i in range(n)]


def test_weekly():
    assert nth(Recurrence.WEEKLY, date(2026, 10, 30), 3) == [date(2026, 10, 30), date(2026, 11, 6), date(2026, 11, 13)]


def test_quarterly_keeps_anchor_day():
    assert nth(Recurrence.QUARTERLY, date(2026, 11, 30), 4) == [
        date(2026, 11, 30), date(2027, 2, 28), date(2027, 5, 30), date(2027, 8, 30),
    ]


def test_yearly_feb_29():
    assert nth(Recurrence.YEARLY, date(2028, 2, 29), 5) == [
        date(2028, 2, 29), date(2029, 2, 28), date(2030, 2, 28), date(2031, 2, 28), date(2032, 2, 29),
    ]


def test_next_due_for_each_strategy():
    assert strategy_for("weekly").next_due(date(2026, 10, 1), date(2026, 10, 8)) == date(2026, 10, 15)
    assert strategy_for("quarterly").next_due(date(2026, 1, 31), date(2026, 4, 30)) == date(2026, 7, 31)
    assert strategy_for("yearly").next_due(date(2028, 2, 29), date(2029, 2, 28)) == date(2030, 2, 28)


def test_plan_weekly_history():
    plan = plan_due_dates("weekly", date(2026, 10, 10), 10, date(2026, 10, 24), set())
    assert plan == [date(2026, 10, 10), date(2026, 10, 17), date(2026, 10, 24), date(2026, 10, 31)]
