"""Форматирование списков платежей в Telegram (только UI, не домен)."""

from __future__ import annotations

import html
from datetime import date
from decimal import Decimal
from itertools import groupby

from app.domain.money import CURRENCY_SYMBOLS, NBSP, Currency, quantize
from app.models import PaymentOccurrence

WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


def when_ru(days: int) -> str:
    if days == 0:
        return "сегодня"
    if days == 1:
        return "завтра"
    return f"через {days} {plural_ru(days, 'день', 'дня', 'дней')}"


def _integer_groups(absq: Decimal) -> str:
    integer = str(int(absq))
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return NBSP.join(groups) if groups else "0"


def format_money_bot(value: Decimal, currency: Currency | str) -> str:
    """Сумма для бота: NBSP, символ валюты, без «,00» у целых."""
    cur = Currency(currency)
    q = quantize(value)
    sign = "-" if q < 0 else ""
    absq = abs(q)
    sym = CURRENCY_SYMBOLS[cur]
    if absq == absq.to_integral_value():
        return f"{sign}{_integer_groups(absq)}{NBSP}{sym}"
    integer, _, frac = f"{absq:.2f}".partition(".")
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    body = NBSP.join(groups)
    return f"{sign}{body},{frac}{NBSP}{sym}"


def short_title(name: str, n: int = 26) -> str:
    raw = name if len(name) <= n else name[: n - 1].rstrip() + "…"
    return html.escape(raw)


def day_header_for_due(d: date, today: date) -> str:
    delta = (d - today).days
    if delta < 0:
        n = -delta
        tail = f"просрочено на {n} {plural_ru(n, 'день', 'дня', 'дней')}"
        return f"🔴 <b>{WD[d.weekday()]}, {d:%d.%m}</b> · {tail}"
    if delta == 0:
        return f"⏰ <b>Сегодня · {d:%d.%m}</b>"
    return f"📅 <b>{WD[d.weekday()]}, {d:%d.%m}</b> · {when_ru(delta)}"


def parse_page_from_message(text: str) -> int:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Страница"):
            try:
                return int(s.split()[1]) - 1
            except (IndexError, ValueError):
                return 0
        if "стр." in s:
            try:
                return int(s.split("стр.", 1)[1].strip().split()[0]) - 1
            except (IndexError, ValueError):
                return 0
    return 0


def render_grouped_payment_lines(
    items: list[PaymentOccurrence], today: date, start_number: int
) -> tuple[list[str], int]:
    """Строки списка с группировкой по due_date; возвращает (lines, next_number)."""
    lines: list[str] = []
    num = start_number
    for due, group in groupby(items, key=lambda o: o.due_date):
        group_list = list(group)
        lines.append(day_header_for_due(due, today))
        lines.append("")
        for o in group_list:
            money = format_money_bot(o.amount_snapshot, o.currency_snapshot)
            lines.append(f"{num}. {short_title(o.title_snapshot)} — <b>{money}</b>")
            num += 1
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines, num


def totals_currency_lines(
    all_items: list[PaymentOccurrence], total_count: int, label: str
) -> list[str]:
    sums: dict[Currency, Decimal] = {}
    for o in all_items:
        c = o.currency_snapshot
        sums[c] = sums.get(c, Decimal(0)) + o.amount_snapshot
    lines = [f"<b>{label} ({total_count}):</b>"]
    for cur in (Currency.RUB, Currency.USD, Currency.EUR):
        if cur not in sums:
            continue
        sym = CURRENCY_SYMBOLS[cur]
        lines.append(f"{sym} {format_money_bot(sums[cur], cur)}")
    return lines


def totals_topay_lines(all_items: list[PaymentOccurrence], total_count: int) -> list[str]:
    return totals_currency_lines(all_items, total_count, "Всего к оплате")


def day_header_paid(d: date) -> str:
    return f"✅ <b>{WD[d.weekday()]}, {d:%d.%m}</b>"


def render_grouped_paid_lines(
    items: list[PaymentOccurrence], start_number: int
) -> tuple[list[str], int]:
    lines: list[str] = []
    num = start_number
    for paid_day, group in groupby(items, key=lambda o: o.paid_date):
        if paid_day is None:
            continue
        group_list = list(group)
        lines.append(day_header_paid(paid_day))
        lines.append("")
        for o in group_list:
            money = format_money_bot(o.amount_snapshot, o.currency_snapshot)
            lines.append(f"{num}. {short_title(o.title_snapshot)} — <b>{money}</b>")
            num += 1
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines, num

