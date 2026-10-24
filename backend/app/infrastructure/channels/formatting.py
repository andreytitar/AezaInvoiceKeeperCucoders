"""Форматирование текстов уведомлений (отдельно для каждого канала)."""

from __future__ import annotations

import html

from app.domain.money import NBSP, format_amount
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
    amount = f"{format_amount(n.amount, n.currency)}{NBSP}({n.currency})"
    return (
        f"Напоминание об оплате: {n.title}\n"
        f"Сумма: {amount}\n"
        f"Дата оплаты: {n.due_date:%d.%m.%Y} ({due_phrase(n.days_until_due)})"
    )


def telegram_html(n: Notification) -> str:
    if n.days_until_due < 0:
        head = "🔴 Просроченный платёж"
    else:
        head = "⏰ Напоминание об оплате"
    amount = html.escape(format_amount(n.amount, n.currency))
    return (
        f"<b>{head}</b>\n\n"
        f"<b>{html.escape(n.title)}</b>\n"
        f"<b>{amount}</b>{NBSP}({html.escape(n.currency)})\n"
        f"Срок: <b>{n.due_date:%d.%m.%Y}</b> — {due_phrase(n.days_until_due)}"
    )
