from datetime import date

import pytest

from app.domain.reminder_policy import should_remind

TODAY = date(2026, 10, 24)


@pytest.mark.parametrize(
    "due, expected",
    [
        (date(2026, 10, 28), False),  # 4 дня
        (date(2026, 10, 27), True),  # ровно 3 дня
        (date(2026, 10, 26), True),
        (date(2026, 10, 24), True),  # день срока
        (date(2026, 10, 1), True),  # просрочено
    ],
)
def test_window(due, expected):
    assert should_remind(due_date=due, is_paid=False, payment_deleted=False, today=TODAY, days_before=3) is expected


def test_paid_never_reminds():
    assert not should_remind(due_date=TODAY, is_paid=True, payment_deleted=False, today=TODAY, days_before=3)


def test_deleted_never_reminds():
    assert not should_remind(due_date=TODAY, is_paid=False, payment_deleted=True, today=TODAY, days_before=3)


def test_larger_window_from_settings():
    assert should_remind(
        due_date=date(2026, 10, 31), is_paid=False, payment_deleted=False, today=TODAY, days_before=7
    )
