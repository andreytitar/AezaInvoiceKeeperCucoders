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


def days_until(due_date: date, today: date) -> int:
    return (due_date - today).days
