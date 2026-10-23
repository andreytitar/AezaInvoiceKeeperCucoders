"""Единственный источник времени в приложении.

Вызовы datetime.now() / date.today() вне этого модуля запрещены (см. tests/unit/test_no_direct_now.py).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime:
        """Текущий момент в UTC (aware)."""
        ...

    def today(self) -> date:
        """Текущая дата в APP_TIMEZONE."""
        ...


class SystemClock:
    def __init__(self, tz: ZoneInfo, fake_today: date | None = None) -> None:
        self.tz = tz
        self.fake_today = fake_today

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        if self.fake_today is not None:
            return self.fake_today
        return datetime.now(self.tz).date()


class FixedClock:
    """Часы для тестов: дата и момент задаются явно и двигаются вручную."""

    def __init__(self, today: date, tz: ZoneInfo | None = None) -> None:
        self.tz = tz or ZoneInfo("Europe/Moscow")
        self._now = datetime.combine(today, time(12, 0), self.tz).astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.astimezone(self.tz).date()

    def set_today(self, d: date) -> None:
        self._now = datetime.combine(d, time(12, 0), self.tz).astimezone(UTC)

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)
