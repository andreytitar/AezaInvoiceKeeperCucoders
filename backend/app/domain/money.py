"""Валюты и денежные суммы. Только Decimal, никогда float."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


CURRENCY_SYMBOLS = {Currency.RUB: "₽", Currency.USD: "$", Currency.EUR: "€"}

# U+00A0. Обычный пробел и узкие пробелы (U+2009, иногда U+202F) Telegram
# считает точкой переноса и режет сумму пополам: «55» / «000,00 ₽».
NBSP = "\u00a0"

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999999999.99")  # NUMERIC(18,2)


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def has_at_most_two_decimals(value: Decimal) -> bool:
    return value == value.quantize(CENT)


def format_amount(value: Decimal, currency: Currency | str) -> str:
    """55000.5 RUB -> '55\\u00a0000,50\\u00a0₽'.

    Группы тысяч и знак валюты склеены неразрывным пробелом, чтобы сумма
    в Telegram (и в остальных текстах уведомлений) оставалась на одной строке.
    """
    cur = Currency(currency)
    q = quantize(value)
    sign = "-" if q < 0 else ""
    integer, _, frac = f"{abs(q):.2f}".partition(".")
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return f"{sign}{NBSP.join(groups)},{frac}{NBSP}{CURRENCY_SYMBOLS[cur]}"
