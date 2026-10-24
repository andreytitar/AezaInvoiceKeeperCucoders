from datetime import date
from decimal import Decimal

from app.domain.money import Currency, NBSP
from app.services.bot_list_format import day_header_for_due, format_money_bot, plural_ru, when_ru


def test_format_money_bot_integer_strips_cents():
    assert format_money_bot(Decimal("1000"), Currency.RUB) == f"1{NBSP}000{NBSP}₽"
    assert ",00" not in format_money_bot(Decimal("75"), Currency.USD)


def test_format_money_bot_fraction():
    assert "9,99" in format_money_bot(Decimal("9.99"), Currency.EUR)


def test_day_header_today_and_future():
    today = date(2026, 10, 24)
    assert "Сегодня" in day_header_for_due(date(2026, 10, 24), today)
    h = day_header_for_due(date(2026, 10, 27), today)
    assert "📅" in h and "через 3 дня" in h


def test_day_header_overdue():
    today = date(2026, 10, 24)
    h = day_header_for_due(date(2026, 10, 19), today)
    assert "🔴" in h and "просрочено на 5 дней" in h


def test_when_plural():
    assert when_ru(2) == "через 2 дня"
    assert plural_ru(11, "день", "дня", "дней") == "дней"
