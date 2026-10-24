"""Подписка на календарь (ICS): личная секретная ссылка пользователя.

В календарь попадают неоплаченные периоды, оплаченные за последние 90 дней и прогноз сроков живых платежей
на 12 месяцев вперёд (прогноз считается той же стратегией дат, в БД не пишется).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.domain.errors import NotFound
from app.domain.ics import CalendarEvent, build_ics
from app.domain.money import format_amount
from app.domain.schedule import strategy_for
from app.domain.status import compute_overdue
from app.models import PaymentOccurrence, User
from app.repositories.payments import PaymentRepository

HORIZON_DAYS = 365
PAID_HISTORY_DAYS = 90


class CalendarFeedService:
    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    def token_for(self, user: User, rotate: bool = False) -> str:
        if rotate or not user.calendar_token:
            user.calendar_token = secrets.token_urlsafe(24)
            self.db.commit()
        return user.calendar_token

    def user_by_token(self, token: str) -> User:
        user = self.db.scalar(select(User).where(User.calendar_token == token, User.deleted_at.is_(None)))
        if user is None:
            raise NotFound("Календарь не найден")
        return user

    def render(self, tz: str) -> str:
        today = self.clock.today()
        events: list[CalendarEvent] = []
        occ = self.db.scalars(
            select(PaymentOccurrence).where(PaymentOccurrence.due_date >= today - timedelta(days=PAID_HISTORY_DAYS))
        ).all()
        occ = [o for o in occ if not o.is_paid or (o.paid_date and o.paid_date >= today - timedelta(days=PAID_HISTORY_DAYS))]
        known: dict = {}
        for o in occ:
            known.setdefault(o.recurring_payment_id, set()).add(o.due_date)
            amount = format_amount(o.amount_snapshot, o.currency_snapshot)
            if o.is_paid:
                summary = f"Оплачено: {o.title_snapshot} — {amount}"
                desc = f"Оплачено {o.paid_date:%d.%m.%Y}"
            else:
                info = compute_overdue(o.due_date, False, None, today)
                summary = f"{'Просрочено: ' if info.is_overdue else 'Оплатить: '}{o.title_snapshot} — {amount}"
                desc = f"Срок {o.due_date:%d.%m.%Y}. Отметить оплату — в панели Invoice Keeper или кнопкой в Telegram."
            if o.payment.deleted_at is not None:
                desc += " Регулярный платёж прекращён."
            events.append(
                CalendarEvent(uid=f"{o.id}@invoice-keeper", day=o.due_date, summary=summary, description=desc,
                              alarms=not o.is_paid and o.due_date >= today)
            )
        # прогноз на год вперёд
        horizon = today + timedelta(days=HORIZON_DAYS)
        for p in PaymentRepository(self.db).list_alive():
            strategy = strategy_for(p.recurrence)
            have = known.get(p.id, set())
            for i in range(0, 600):
                d = strategy.nth_due(p.first_due_date, p.anchor_day, i)
                if d > horizon:
                    break
                if d < today or d in have:
                    continue
                events.append(
                    CalendarEvent(
                        uid=f"{p.id}-{d:%Y%m%d}@invoice-keeper",
                        day=d,
                        summary=f"Оплатить: {p.title} — {format_amount(p.amount, p.currency)}",
                        description="Плановый срок регулярного платежа.",
                    )
                )
        events.sort(key=lambda e: (e.day, e.summary))
        return build_ics("Invoice Keeper — платежи", events, self.clock.now(), tz)


