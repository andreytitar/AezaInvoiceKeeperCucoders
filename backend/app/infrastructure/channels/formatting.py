"""Форматирование текстов уведомлений (отдельно для каждого канала)."""

from __future__ import annotations

import html

from app.domain.money import format_amount
from app.infrastructure.channels.base import Notification


def due_phrase(days: int) -> str:
    if days > 1:
        return f"через {days} дн."
    if days == 1:
        return "завтра"
    if days == 0:
        return "сегодня"
    return f"просрочено на {-days} дн."


def plain_text(n: Notification) -> str:
    return (
        f"Напоминание об оплате: {n.title}\n"
        f"Сумма: {format_amount(n.amount, n.currency)} ({n.currency})\n"
        f"Дата оплаты: {n.due_date:%d.%m.%Y} ({due_phrase(n.days_until_due)})"
    )


def telegram_html(n: Notification) -> str:
    head = "Просроченный платёж" if n.days_until_due < 0 else "Напоминание об оплате"
    return (
        f"<b>{head}</b>\n\n"
        f"<b>{html.escape(n.title)}</b>\n"
        f"Сумма: <b>{html.escape(format_amount(n.amount, n.currency))}</b> ({n.currency})\n"
        f"Дата оплаты: <b>{n.due_date:%d.%m.%Y}</b> — {due_phrase(n.days_until_due)}"
    )
