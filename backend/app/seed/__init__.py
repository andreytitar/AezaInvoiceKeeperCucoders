"""Идемпотентный сид демо-данных: `python -m app.seed` (make seed) или SEED_ON_START=true.

Даты считаются от «сегодня» (Clock, учитывает APP_FAKE_TODAY), чтобы демо всегда было живым:
- Аренда офиса, 55 000 RUB: период оплачен в срок, период оплачен с опозданием, ближайший — через 12 дней;
- Сервер Aeza, 25 USD: срок через 2 дня — напоминание уходит сразу;
- Подписка JetBrains, 9.99 EUR: просрочена на 5 дней;
- Облачное хранилище, 12.50 USD: якорь 31-го числа (31 -> 30 -> 31 ...);
- пользователи ivan и maria с паролем SEED_USER_PASSWORD.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.container import Container
from app.domain.money import Currency
from app.domain.schedule import add_months, days_in_month
from app.domain.status import PaymentStatus
from app.models import AppMeta
from app.repositories.payments import OccurrenceRepository, PaymentRepository
from app.repositories.teams import TeamRepository
from app.repositories.users import UserRepository
from app.services.occurrences import OccurrenceService
from app.services.payments import PaymentService
from app.services.users import UserService

log = logging.getLogger("app.seed")

SEED_KEY = "seed_v1"
SEED_USERS = ("ivan", "maria")


def next_day_31(today: date) -> date:
    d = today
    while True:
        if days_in_month(d.year, d.month) == 31:
            candidate = date(d.year, d.month, 31)
            if candidate >= today:
                return candidate
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=1)


def _mark(db: DbSession, c: Container, payment_id, due: date, paid: date) -> None:
    occ = next(o for o in OccurrenceRepository(db).list_for_payment(payment_id) if o.due_date == due)
    OccurrenceService(db, c.clock, c.settings).mark(
        occ.id, status=PaymentStatus.PAID, paid_date=paid, paid_date_provided=True, actor=None
    )


def run_seed(c: Container, force: bool = False) -> bool:
    with c.session_factory() as db:
        if not force and db.get(AppMeta, SEED_KEY) is not None:
            log.info("Сид уже применён — пропускаю")
            return False
        today = c.clock.today()
        primary = TeamRepository(db).ensure_primary()
        users = UserService(db, c.clock, c.settings)
        for login in SEED_USERS:
            if UserRepository(db).get_by_login(login) is None:
                users.create(login=login, password=c.settings.seed_user_password, team_id=primary.id)

        payments = PaymentService(db, c.clock, c.settings, c.channels)
        repo = PaymentRepository(db)

        def ensure(title: str, amount: str, currency: Currency, first_due: date):
            existing = repo.find_by_title(title, team_id=primary.id)
            if existing:
                return existing, False
            return payments.create(
                title=title, amount=Decimal(amount), currency=currency, first_due_date=first_due, actor=None
            ), True

        rent_first = add_months(today + timedelta(days=12), -2)
        rent, created = ensure("Аренда офиса", "55000.00", Currency.RUB, rent_first)
        if created:
            p0 = rent_first
            p1 = add_months(rent_first, 1, rent.anchor_day)
            _mark(db, c, rent.id, p0, p0 - timedelta(days=1))  # в срок
            _mark(db, c, rent.id, p1, min(p1 + timedelta(days=3), today))  # с опозданием
        ensure("Сервер Aeza", "25.00", Currency.USD, today + timedelta(days=2))
        ensure("Подписка JetBrains", "9.99", Currency.EUR, today - timedelta(days=5))
        ensure("Облачное хранилище", "12.50", Currency.USD, next_day_31(today))

        if db.get(AppMeta, SEED_KEY) is None:
            db.add(AppMeta(key=SEED_KEY, value=today.isoformat()))
        db.commit()
        log.info("Демо-данные созданы (пользователи: %s)", ", ".join(SEED_USERS))
        return True


def main() -> None:
    import sys

    from app.container import build_container
    from app.infrastructure.logging import setup_logging

    c = build_container()
    setup_logging(c.settings.log_level)
    run_seed(c, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
