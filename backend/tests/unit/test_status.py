from datetime import date

import pytest

from app.domain.errors import ValidationError
from app.domain.status import PaymentStatus, apply_status_change, compute_overdue

DUE = date(2026, 10, 10)


def test_unpaid_on_due_date_is_not_overdue():
    assert compute_overdue(DUE, False, None, DUE).is_overdue is False


def test_unpaid_overdue_starts_next_day():
    info = compute_overdue(DUE, False, None, date(2026, 10, 11))
    assert info.is_overdue and info.overdue_days == 1


def test_unpaid_future_not_overdue():
    info = compute_overdue(DUE, False, None, date(2026, 10, 1))
    assert not info.is_overdue and info.overdue_days == 0


def test_paid_on_due_date_is_on_time():
    info = compute_overdue(DUE, True, DUE, date(2026, 12, 1))
    assert not info.is_overdue and info.overdue_days == 0


def test_paid_early_is_on_time():
    assert compute_overdue(DUE, True, date(2026, 10, 1), date(2026, 12, 1)).is_overdue is False


def test_paid_late_is_marked_with_days():
    info = compute_overdue(DUE, True, date(2026, 10, 13), date(2026, 12, 1))
    assert info.is_overdue and info.overdue_days == 3


def test_paid_late_does_not_grow_with_today():
    a = compute_overdue(DUE, True, date(2026, 10, 13), date(2026, 10, 20))
    b = compute_overdue(DUE, True, date(2026, 10, 13), date(2027, 1, 1))
    assert a == b


TODAY = date(2026, 10, 24)


def change(**kw):
    base = dict(
        current_is_paid=False,
        current_paid_date=None,
        new_status=PaymentStatus.PAID,
        paid_date=None,
        paid_date_provided=False,
        today=TODAY,
    )
    base.update(kw)
    return apply_status_change(**base)


def test_mark_paid_without_date_uses_today():
    assert change().paid_date == TODAY


def test_mark_paid_with_date():
    m = change(paid_date=date(2026, 10, 20), paid_date_provided=True)
    assert m.is_paid and m.paid_date == date(2026, 10, 20)


def test_paid_date_in_future_rejected():
    with pytest.raises(ValidationError):
        change(paid_date=date(2026, 10, 25), paid_date_provided=True)


def test_unmark_clears_date():
    m = change(current_is_paid=True, current_paid_date=date(2026, 10, 1), new_status=PaymentStatus.UNPAID)
    assert m.is_paid is False and m.paid_date is None


def test_date_with_unpaid_status_rejected():
    with pytest.raises(ValidationError):
        change(new_status=PaymentStatus.UNPAID, paid_date=date(2026, 10, 1), paid_date_provided=True)


def test_repeat_mark_paid_keeps_existing_date():
    m = change(current_is_paid=True, current_paid_date=date(2026, 10, 1))
    assert m.paid_date == date(2026, 10, 1)


def test_correcting_date_recomputes_overdue_without_touching_due():
    # ошибочно отметили 15-м числом (просрочка 5 дней), исправили на 9-е — просрочки нет
    wrong = change(paid_date=date(2026, 10, 15), paid_date_provided=True)
    assert compute_overdue(DUE, wrong.is_paid, wrong.paid_date, TODAY).overdue_days == 5
    fixed = change(
        current_is_paid=True, current_paid_date=wrong.paid_date, paid_date=date(2026, 10, 9), paid_date_provided=True
    )
    assert compute_overdue(DUE, fixed.is_paid, fixed.paid_date, TODAY).is_overdue is False
