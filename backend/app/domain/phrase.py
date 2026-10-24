"""Разбор фразы «аренда 55000 руб каждое 5-е» в регулярный платёж. Без I/O и без ИИ: предсказуемо.

Понимает:
- сумму: 55000, 55 000, 9.99, 9,99; валюту: руб/р/₽/rub, $/usd/долл, €/eur/евро (по умолчанию RUB);
- периодичность: ежемесячно (по умолчанию), еженедельно/каждую неделю, ежеквартально/раз в квартал,
  ежегодно/раз в год;
- дату: 05.11, 05.11.2026, «каждое 5-е», «5 числа», «5-го», сегодня, завтра, «через 3 дня».
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.domain.errors import ValidationError
from app.domain.money import Currency, has_at_most_two_decimals
from app.domain.schedule import Recurrence, add_months, month_date

CURRENCY_WORDS = [
    (r"(?:руб(?:л(?:ей|я|ь))?\.?|р\.?|₽|rub|rur)", Currency.RUB),
    (r"(?:\$|usd|долл(?:ар(?:ов|а)?)?\.?|бакс(?:ов|а)?)", Currency.USD),
    (r"(?:€|eur|евро)", Currency.EUR),
]
RECURRENCE_WORDS = [
    (r"еженедельн\w*|кажд\w* недел\w*|раз в неделю", Recurrence.WEEKLY),
    (r"ежекварт\w*|раз в квартал|кажд\w* квартал\w*", Recurrence.QUARTERLY),
    (r"ежегодн\w*|раз в год|кажд\w* год\w*", Recurrence.YEARLY),
    (r"ежемесячн\w*|раз в месяц|кажд\w* месяц\w*", Recurrence.MONTHLY),
]
NUM = r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"

_ADD_EXAMPLE = "Добавить платёж можно так: /add аренда 55000 руб каждое 5-е"


def _phrase_error(problem: str) -> str:
    return f"{problem} {_ADD_EXAMPLE}"


@dataclass(frozen=True)
class ParsedPayment:
    title: str
    amount: Decimal
    currency: Currency
    first_due_date: date
    recurrence: Recurrence


def _amount(raw: str) -> Decimal:
    try:
        value = Decimal(raw.replace(" ", "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise ValidationError(_phrase_error("Не получилось прочитать сумму.")) from None
    if value <= 0:
        raise ValidationError(_phrase_error("Укажите сумму больше нуля."))
    if not has_at_most_two_decimals(value):
        raise ValidationError(_phrase_error("Укажите не больше двух знаков после запятой."))
    return value


def _next_day_of_month(day: int, today: date) -> date:
    if not 1 <= day <= 31:
        raise ValidationError(_phrase_error("Укажите день месяца от 1 до 31."))
    d = month_date(today.year, today.month, day)
    return d if d >= today else add_months(today.replace(day=1), 1, day)


def parse_payment_phrase(text: str, today: date) -> ParsedPayment:
    src = " " + " ".join(text.split()) + " "
    low = src.lower()
    used: list[tuple[int, int]] = []

    def take(m: re.Match) -> None:
        used.append(m.span())

    # периодичность
    recurrence = Recurrence.MONTHLY
    for pattern, rec in RECURRENCE_WORDS:
        m = re.search(pattern, low)
        if m:
            recurrence = rec
            take(m)
            break

    # дата
    due: date | None = None
    m = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?(?![\d.])", low)
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), m.group(3)
        year = (2000 + int(yy) if len(yy) == 2 else int(yy)) if yy else today.year
        try:
            due = date(year, mm, dd)
        except ValueError:
            raise ValidationError(_phrase_error(f"Нет такой даты: {m.group(0).strip()}.")) from None
        if not yy and due < today:
            due = date(year + 1, mm, dd)
        take(m)
    if due is None:
        m = re.search(r"(?:кажд\w*|с)?\s*(\d{1,2})\s*(?:-?(?:е|го|ое|ого)\b|\s*числ\w*)", low)
        if m:
            due = _next_day_of_month(int(m.group(1)), today)
            take(m)
    if due is None:
        for pattern, delta in ((r"\bсегодня\b", 0), (r"\bзавтра\b", 1), (r"\bпослезавтра\b", 2)):
            m = re.search(pattern, low)
            if m:
                due = today + timedelta(days=delta)
                take(m)
                break
    if due is None:
        m = re.search(r"через\s+(\d{1,3})\s*д\w*", low)
        if m:
            due = today + timedelta(days=int(m.group(1)))
            take(m)

    # сумма и валюта (валюта до или после числа)
    currency = None
    amount = None
    for cur_pattern, cur in CURRENCY_WORDS:
        m = re.search(rf"(?<![\d.,])({NUM})\s*{cur_pattern}(?=\s|$|[.,!])", low)
        if m is None:  # символ валюты перед числом: $25, € 9.99
            m = re.search(rf"(?<![\w])[$€₽]\s*({NUM})(?![\d.,])", low) if cur.value in ("USD", "EUR", "RUB") else None
            if m and {"$": Currency.USD, "€": Currency.EUR, "₽": Currency.RUB}[m.group(0).strip()[0]] != cur:
                m = None
        if m and not any(a <= m.start() < b for a, b in used):
            amount, currency = _amount(m.group(1)), cur
            take(m)
            break
    if amount is None:
        for m in re.finditer(rf"(?<![\w.])({NUM})(?![\w.])", low):
            if not any(a <= m.start() < b for a, b in used):
                amount, currency = _amount(m.group(1)), Currency.RUB
                take(m)
                break
    if amount is None:
        raise ValidationError(_phrase_error("Не вижу сумму."))
    if due is None:
        raise ValidationError(_phrase_error("Не вижу дату."))

    # название — всё, что осталось
    chars = list(src)
    for a, b in used:
        for i in range(a, b):
            chars[i] = " "
    title = re.sub(r"\b(с|каждое|каждый|числа|по|за)\b", " ", "".join(chars), flags=re.IGNORECASE)
    title = " ".join(title.replace(",", " ").split()).strip(" -—:")
    if not title:
        raise ValidationError(_phrase_error("Не вижу название."))
    title = title[0].upper() + title[1:]
    return ParsedPayment(title[:200], amount, currency or Currency.RUB, due, recurrence)
