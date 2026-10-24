"""Суммы в текстах Telegram не рвутся переносом по обычному пробелу."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.domain.clock import FixedClock
from app.domain.money import NBSP, Currency, format_amount
from app.infrastructure.channels.base import Notification
from app.infrastructure.channels.chat_webhook import render
from app.infrastructure.channels.formatting import plain_text, telegram_html
from app.services.bot_answers import BotAnswers, _money, _totals, format_occurrence_card

GROUPED_ON_REGULAR_SPACE = re.compile(r"\d \d")


def _visible(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _tokens(text: str) -> list[str]:
    return re.split(r"[ \t\r\n]+", _visible(text).strip())


def _assert_atomic(text: str, fragment: str) -> None:
    visible = _visible(text)
    assert fragment in visible
    assert " " not in fragment
    assert NBSP in fragment
    assert any(fragment in token for token in _tokens(text))
    assert GROUPED_ON_REGULAR_SPACE.search(visible) is None
    assert "&nbsp;" not in text


def _notice(amount: str, currency: str, days: int = 2) -> Notification:
    return Notification(
        occurrence_id=uuid.uuid4(),
        title="Аренда офиса на очень длинной улице",
        amount=Decimal(amount),
        currency=currency,
        due_date=date(2026, 10, 26),
        days_until_due=days,
    )


def test_reminder_and_overdue_keep_amount_and_currency_together():
    for days in (2, -3):
        n = _notice("1234567.5", "USD", days)
        glued = f"{format_amount(n.amount, n.currency)}{NBSP}(USD)"
        for text in (telegram_html(n), plain_text(n)):
            _assert_atomic(text, glued)
            assert "26.10.2026" in _tokens(text)


def test_small_amount_symbol_does_not_wrap():
    n = _notice("9.99", "EUR", 0)
    glued = f"{format_amount(n.amount, n.currency)}{NBSP}(EUR)"
    _assert_atomic(telegram_html(n), glued)
    assert glued == f"9,99{NBSP}€{NBSP}(EUR)"


def test_chat_webhook_amount_is_atomic():
    n = _notice("55000", "RUB")
    glued = f"{format_amount(n.amount, n.currency)}{NBSP}(RUB)"
    for fmt in ("slack", "discord", "mattermost"):
        body = render(n, fmt)
        text = body.get("text") or body["content"]
        _assert_atomic(text, glued)


def test_bot_list_line_does_not_split_amount_or_date():
    answers = BotAnswers(db=None, clock=FixedClock(date(2026, 10, 24)))
    item = SimpleNamespace(
        due_date=date(2026, 10, 28),
        is_paid=False,
        paid_date=None,
        title_snapshot="Аренда офиса на очень длинной улице",
        amount_snapshot=Decimal("55000"),
        currency_snapshot=Currency.RUB,
    )
    line = format_occurrence_card(item, date(2026, 10, 24))
    amount = format_amount(item.amount_snapshot, item.currency_snapshot)
    glued = f"{amount}{NBSP}({item.currency_snapshot.value})"
    _assert_atomic(line, glued)
    assert "28.10.2026" in _visible(line)
    assert _money(item) == amount


def test_bot_totals_keep_each_sum_atomic():
    items = [
        SimpleNamespace(amount_snapshot=Decimal("55000"), currency_snapshot=Currency.RUB),
        SimpleNamespace(amount_snapshot=Decimal("1500"), currency_snapshot=Currency.RUB),
        SimpleNamespace(amount_snapshot=Decimal("9.99"), currency_snapshot=Currency.EUR),
    ]
    text = _totals(items)
    assert format_amount(Decimal("56500"), Currency.RUB) in text
    assert format_amount(Decimal("9.99"), Currency.EUR) in text
    assert GROUPED_ON_REGULAR_SPACE.search(text) is None
    for token in _tokens(text):
        if NBSP in token:
            assert " " not in token
