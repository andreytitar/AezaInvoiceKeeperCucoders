"""Форматирование UI бота: карточки, nav callback, пагинация."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.domain.clock import FixedClock
from app.domain.money import Currency
from app.services.bot_answers import (
    format_occurrence_card,
    list_paid_callback,
    nav_callback,
    parse_list_paid_callback,
    parse_nav_callback,
    screen_from_message_text,
)


def _occ(**kw):
    defaults = dict(
        due_date=date(2026, 10, 28),
        is_paid=False,
        paid_date=None,
        title_snapshot="Аренда",
        amount_snapshot=Decimal("55000"),
        currency_snapshot=Currency.RUB,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_format_occurrence_card_unpaid():
    today = date(2026, 10, 24)
    text = format_occurrence_card(_occ(), today)
    assert "⏰" in text and "Аренда" in text and "через 4 дн." in text


def test_format_occurrence_card_overdue():
    today = date(2026, 10, 30)
    text = format_occurrence_card(_occ(due_date=date(2026, 10, 20)), today)
    assert "🔴" in text and "просрочено на" in text


def test_format_occurrence_card_paid():
    today = date(2026, 10, 24)
    text = format_occurrence_card(
        _occ(is_paid=True, paid_date=date(2026, 10, 24), due_date=date(2026, 10, 24)),
        today,
    )
    assert "✅" in text and "оплачено" in text


def test_nav_callback_roundtrip():
    assert parse_nav_callback(nav_callback("topay", 2)) == ("topay", 2)
    assert parse_nav_callback(nav_callback("menu")) == ("menu", 0)
    assert parse_nav_callback("nav:zzz") is None


def test_list_paid_callback_legacy_and_new():
    oid = uuid.uuid4()
    assert parse_list_paid_callback(f"lp:{oid}") == (None, str(oid))
    assert parse_list_paid_callback(list_paid_callback("week", oid)) == ("week", str(oid))


def test_screen_from_message_heuristic():
    assert screen_from_message_text("🔴 <b>Просрочено</b> · 1 платёж") == "overdue"
    assert screen_from_message_text("📅 <b>На неделю</b> · 1 платёж") == "week"
    assert screen_from_message_text("💳 <b>К оплате</b> · 2 платежа") == "topay"
