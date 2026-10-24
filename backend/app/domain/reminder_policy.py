"""Политика напоминаний: чистая функция без I/O."""

from __future__ import annotations

from datetime import date, timedelta


def reminder_window_end(today: date, days_before: int) -> date:
    """Периоды со сроком <= этой даты попадают под напоминание (включая просроченные)."""
    return today + timedelta(days=days_before)


def should_remind(
    *,
    due_date: date,
    is_paid: bool,
    payment_deleted: bool,
    today: date,
    days_before: int,
) -> bool:
    """Напоминать, если период не оплачен, платёж не удалён и до срока осталось <= days_before дней
    (включая сам день срока и просроченные периоды). Отсутствие дублей обеспечивает таблица доставок."""
    if is_paid or payment_deleted:
        return False
    return due_date <= reminder_window_end(today, days_before)


def overdue_repeat_bucket(overdue_days: int, every_days: int, max_repeats: int) -> int | None:
    """Номер повтора «просрочено» для текущего дня просрочки или None.

    Повторы на 1-й, 1+every-й, 1+2·every-й … день просрочки, не больше max_repeats.
    Номер — часть ключа доставки, поэтому каждый повтор уходит ровно один раз.
    """
    if every_days <= 0 or max_repeats <= 0 or overdue_days < 1:
        return None
    bucket = (overdue_days - 1) // every_days
    return bucket if bucket < max_repeats else None


def days_until(due_date: date, today: date) -> int:
    return (due_date - today).days
