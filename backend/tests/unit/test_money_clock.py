from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.clock import FixedClock, SystemClock
from app.domain.money import format_amount, has_at_most_two_decimals


def test_format_amount():
    assert format_amount(Decimal("55000"), "RUB") == "55 000,00 ₽"
    assert format_amount(Decimal("9.99"), "EUR") == "9,99 €"
    assert format_amount(Decimal("1234567.5"), "USD") == "1 234 567,50 $"


def test_two_decimals():
    assert has_at_most_two_decimals(Decimal("1.25"))
    assert not has_at_most_two_decimals(Decimal("1.255"))


def test_fixed_clock_today_in_timezone():
    c = FixedClock(date(2026, 10, 24))
    assert c.today() == date(2026, 10, 24)
    assert c.now().tzinfo is UTC
    c.advance(days=1)
    assert c.today() == date(2026, 10, 25)


def test_system_clock_fake_today():
    c = SystemClock(ZoneInfo("Europe/Moscow"), fake_today=date(2030, 1, 1))
    assert c.today() == date(2030, 1, 1)
    assert isinstance(c.now(), datetime) and c.now().tzinfo is not None
