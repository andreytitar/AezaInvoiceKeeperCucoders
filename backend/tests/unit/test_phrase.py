from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import ValidationError
from app.domain.phrase import parse_payment_phrase

TODAY = date(2026, 10, 24)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("аренда 55000 руб каждое 5-е", ("Аренда", "55000", "RUB", date(2026, 11, 5), "monthly")),
        ("Сервер Aeza 25$ 28 числа", ("Сервер Aeza", "25", "USD", date(2026, 10, 28), "monthly")),
        ("подписка JetBrains 9,99 eur 19.11", ("Подписка JetBrains", "9.99", "EUR", date(2026, 11, 19), "monthly")),
        ("домен $12 ежегодно 01.12.2026", ("Домен", "12", "USD", date(2026, 12, 1), "yearly")),
        ("уборка 3 000 р еженедельно с 28.10", ("Уборка", "3000", "RUB", date(2026, 10, 28), "weekly")),
        ("налог 10000 ₽ ежеквартально 31-го", ("Налог", "10000", "RUB", date(2026, 10, 31), "quarterly")),
        ("интернет 900 завтра", ("Интернет", "900", "RUB", date(2026, 10, 25), "monthly")),
        ("хостинг 15 евро через 3 дня", ("Хостинг", "15", "EUR", date(2026, 10, 27), "monthly")),
        ("связь 500 руб 10.01", ("Связь", "500", "RUB", date(2027, 1, 10), "monthly")),  # 10.01 уже прошло -> след. год
    ],
)
def test_parse(text, expected):
    p = parse_payment_phrase(text, TODAY)
    assert (p.title, str(p.amount.normalize()) if p.amount == p.amount.to_integral() else str(p.amount),
            p.currency.value, p.first_due_date, p.recurrence.value) == (
        expected[0], str(Decimal(expected[1]).normalize()) if Decimal(expected[1]) == Decimal(expected[1]).to_integral() else expected[1],
        expected[2], expected[3], expected[4])


def test_day_of_month_already_passed_goes_next_month():
    assert parse_payment_phrase("аренда 1000 каждое 20-е", TODAY).first_due_date == date(2026, 11, 20)


def test_day_31_clamped():
    assert parse_payment_phrase("аренда 1000 каждое 31-е", date(2026, 11, 2)).first_due_date == date(2026, 11, 30)


@pytest.mark.parametrize("text", ["аренда каждое 5-е", "аренда 1000", "55000 руб 5 числа", "аренда 1000 руб 31.02", "аренда 1.555 руб 5 числа"])
def test_errors(text):
    with pytest.raises(ValidationError):
        parse_payment_phrase(text, TODAY)
