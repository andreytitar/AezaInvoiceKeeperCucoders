"""Жизненный цикл команд: основная при старте, песочница из бота, удаление просроченных."""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import Conflict, TooManyRequests, ValidationError
from app.domain.money import Currency
from app.infrastructure.security import hash_password
from app.models import (
    AuditLog,
    Budget,
    NotificationDelivery,
    PaymentOccurrence,
    Receipt,
    RecurringPayment,
    Role,
    Session,
    Team,
    TeamKind,
    TelegramLinkCode,
    User,
    WebhookEndpoint,
)
from app.repositories.teams import TeamRepository
from app.repositories.users import UserRepository
from app.services.payments import PaymentService
from app.services.telegram_link import TelegramLinkService

log = logging.getLogger("app.teams")

SANDBOX_TTL = timedelta(hours=24)
SANDBOX_PER_MINUTE = 5
MAGIC_TTL = timedelta(hours=24)


@dataclass
class SandboxCreated:
    team_id: uuid.UUID
    admin_id: uuid.UUID
    admin_login: str
    employee_id: uuid.UUID
    employee_login: str
    admin_code: str
    employee_code: str
    invite_code: str
    expires_at: datetime


class TeamService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.teams = TeamRepository(db)
        self.users = UserRepository(db)

    def create_sandbox(self, telegram_user_id: int) -> SandboxCreated:
        if self.users.get_by_telegram_id(telegram_user_id) is not None:
            raise Conflict("Этот Telegram уже состоит в команде", code="telegram_taken")
        since = self.clock.now() - timedelta(minutes=1)
        if self.teams.count_sandboxes_created_since(since) >= SANDBOX_PER_MINUTE:
            raise TooManyRequests("Слишком много временных команд, попробуйте через минуту")
        now = self.clock.now()
        invite = secrets.token_hex(4).upper()
        team = self.teams.add(
            Team(
                kind=TeamKind.SANDBOX,
                name="Временная команда",
                expires_at=now + SANDBOX_TTL,
                invite_code=invite,
                created_at=now,
                updated_at=now,
            )
        )
        admin = self.users.add(
            User(
                team_id=team.id,
                login=self._free_login("sandbox"),
                password_hash=hash_password(secrets.token_urlsafe(18)),
                role=Role.ADMIN,
                is_system=False,
                telegram_user_id=telegram_user_id,
            )
        )
        employee = self.users.add(
            User(
                team_id=team.id,
                login=self._free_login("sotrudnik"),
                password_hash=hash_password(secrets.token_urlsafe(18)),
                role=Role.USER,
                is_system=False,
            )
        )
        self._demo_payments(admin)
        links = TelegramLinkService(self.db, self.clock, self.settings)
        admin_magic = links.create_magic(admin, MAGIC_TTL)
        employee_magic = links.create_magic(employee, MAGIC_TTL)
        self.db.commit()
        log.info("Создана временная команда", extra={"team_id": str(team.id), "telegram_user_id": telegram_user_id})
        return SandboxCreated(
            team_id=team.id,
            admin_id=admin.id,
            admin_login=admin.login,
            employee_id=employee.id,
            employee_login=employee.login,
            admin_code=admin_magic.code,
            employee_code=employee_magic.code,
            invite_code=invite,
            expires_at=team.expires_at,
        )

    def join_by_invite(self, telegram_user_id: int, code: str) -> User:
        if self.users.get_by_telegram_id(telegram_user_id) is not None:
            raise Conflict("Этот Telegram уже состоит в команде", code="telegram_taken")
        team = self.teams.get_by_invite(code)
        if team is None or team.kind != TeamKind.SANDBOX:
            raise ValidationError("Код приглашения не найден")
        if team.expires_at is not None and team.expires_at <= self.clock.now():
            raise ValidationError("Срок временной команды истёк")
        user = self.users.add(
            User(
                team_id=team.id,
                login=self._free_login(f"tg{telegram_user_id}"),
                password_hash=hash_password(secrets.token_urlsafe(18)),
                role=Role.USER,
                is_system=False,
                telegram_user_id=telegram_user_id,
            )
        )
        self.db.commit()
        return user

    def magic_for(self, user: User) -> str:
        """Свежая одноразовая ссылка входа (повторный /start в песочнице)."""
        ttl = MAGIC_TTL
        if user.team.expires_at is not None:
            left = user.team.expires_at - self.clock.now()
            if left <= timedelta(0):
                raise ValidationError("Срок временной команды истёк")
            ttl = min(ttl, left)
        code = TelegramLinkService(self.db, self.clock, self.settings).create_magic(user, ttl)
        return code.code

    def employee_of(self, team_id: uuid.UUID) -> User | None:
        return self.db.scalar(
            select(User).where(
                User.team_id == team_id,
                User.role == Role.USER,
                User.deleted_at.is_(None),
                User.is_system.is_(False),
            ).order_by(User.created_at)
        )

    def purge_expired(self) -> int:
        now = self.clock.now()
        removed = 0
        for team in self.teams.expired_sandboxes(now):
            self._purge(team.id)
            removed += 1
        if removed:
            self.db.commit()
            log.info("Удалено просроченных временных команд: %s", removed)
        return removed

    def _free_login(self, prefix: str) -> str:
        prefix = prefix[:40]
        for _ in range(8):
            login = f"{prefix}-{secrets.token_hex(2)}"
            if self.users.get_by_login(login) is None and login.lower() != self.settings.admin_login.lower():
                return login
        return f"{prefix}-{secrets.token_hex(6)}"

    def _demo_payments(self, admin: User) -> None:
        """Три демо-платежа как в сиде: аренда RUB (ещё не скоро), сервер USD (≤3 дней), подписка EUR (просрочка)."""
        today = self.clock.today()
        payments = PaymentService(self.db, self.clock, self.settings, channels=None)
        payments.create(
            title="Аренда офиса",
            amount=Decimal("55000.00"),
            currency=Currency.RUB,
            first_due_date=today + timedelta(days=12),
            actor=admin,
        )
        payments.create(
            title="Сервер Aeza",
            amount=Decimal("25.00"),
            currency=Currency.USD,
            first_due_date=today + timedelta(days=2),
            actor=admin,
        )
        payments.create(
            title="Подписка JetBrains",
            amount=Decimal("9.99"),
            currency=Currency.EUR,
            first_due_date=today - timedelta(days=5),
            actor=admin,
        )

    def _purge(self, team_id: uuid.UUID) -> None:
        user_ids = list(self.db.scalars(select(User.id).where(User.team_id == team_id)))
        payment_ids = list(self.db.scalars(select(RecurringPayment.id).where(RecurringPayment.team_id == team_id)))
        occ_ids = []
        if payment_ids:
            occ_ids = list(
                self.db.scalars(
                    select(PaymentOccurrence.id).where(PaymentOccurrence.recurring_payment_id.in_(payment_ids))
                )
            )
        if occ_ids:
            self.db.execute(delete(NotificationDelivery).where(NotificationDelivery.occurrence_id.in_(occ_ids)))
            self.db.execute(delete(Receipt).where(Receipt.occurrence_id.in_(occ_ids)))
            self.db.execute(delete(PaymentOccurrence).where(PaymentOccurrence.id.in_(occ_ids)))
        if payment_ids:
            self.db.execute(delete(RecurringPayment).where(RecurringPayment.id.in_(payment_ids)))
        if user_ids:
            self.db.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id.in_(user_ids)))
            self.db.execute(delete(Session).where(Session.user_id.in_(user_ids)))
            self.db.execute(delete(User).where(User.id.in_(user_ids)))
        self.db.execute(delete(AuditLog).where(AuditLog.team_id == team_id))
        self.db.execute(delete(WebhookEndpoint).where(WebhookEndpoint.team_id == team_id))
        self.db.execute(delete(Budget).where(Budget.team_id == team_id))
        self.db.execute(delete(Team).where(Team.id == team_id))
        self.db.flush()
