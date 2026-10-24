"""SQLAlchemy-модели. Деньги — NUMERIC(18,2), сроки — DATE, метки времени — timestamptz (UTC)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.money import Currency
from app.domain.schedule import Recurrence


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class TeamKind(StrEnum):
    PRIMARY = "primary"
    SANDBOX = "sandbox"


class BudgetPeriod(StrEnum):
    MONTH = "month"
    YEAR = "year"


class DeliveryKind(StrEnum):
    REMINDER = "reminder"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Team(TimestampMixin, Base):
    """Команда: одна основная (primary) и временные песочницы из бота (sandbox, 24 часа)."""

    __tablename__ = "teams"
    __table_args__ = (
        Index("uq_teams_one_primary", "kind", unique=True, postgresql_where=text("kind = 'primary'")),
        Index(
            "uq_teams_chat",
            "telegram_chat_id",
            unique=True,
            postgresql_where=text("telegram_chat_id IS NOT NULL"),
        ),
        Index(
            "uq_teams_invite",
            "invite_code",
            unique=True,
            postgresql_where=text("invite_code IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[TeamKind] = mapped_column(_enum(TeamKind, "team_kind"))
    name: Mapped[str] = mapped_column(String(120))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_chat_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_bound_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invite_code: Mapped[str | None] = mapped_column(String(32), nullable=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_login_alive", "login", unique=True, postgresql_where=text("deleted_at IS NULL")),
        UniqueConstraint("calendar_token", name="uq_users_calendar_token"),
        Index(
            "uq_users_telegram_alive",
            "telegram_user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND telegram_user_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    login: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.USER)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    calendar_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    team: Mapped[Team] = relationship(lazy="joined")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()


class RecurringPayment(TimestampMixin, Base):
    __tablename__ = "recurring_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_recurring_payments_amount_positive"),
        CheckConstraint("anchor_day BETWEEN 1 AND 31", name="ck_recurring_payments_anchor_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[Currency] = mapped_column(_enum(Currency, "currency"))
    recurrence: Mapped[Recurrence] = mapped_column(
        _enum(Recurrence, "recurrence"), default=Recurrence.MONTHLY, server_default=Recurrence.MONTHLY.value
    )
    first_due_date: Mapped[date] = mapped_column(Date)
    anchor_day: Mapped[int] = mapped_column(SmallInteger)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentOccurrence(TimestampMixin, Base):
    __tablename__ = "payment_occurrences"
    __table_args__ = (
        UniqueConstraint("recurring_payment_id", "due_date", name="uq_occurrence_payment_due"),
        CheckConstraint("is_paid OR paid_date IS NULL", name="ck_occurrence_unpaid_no_date"),
        CheckConstraint("NOT is_paid OR paid_date IS NOT NULL", name="ck_occurrence_paid_has_date"),
        CheckConstraint("amount_snapshot > 0", name="ck_occurrence_amount_positive"),
        Index("ix_occurrence_due_date", "due_date"),
        Index("ix_occurrence_paid_due", "is_paid", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recurring_payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recurring_payments.id", ondelete="RESTRICT"), index=True
    )
    title_snapshot: Mapped[str] = mapped_column(String(200))
    amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency_snapshot: Mapped[Currency] = mapped_column(_enum(Currency, "currency"))
    due_date: Mapped[date] = mapped_column(Date)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    payment: Mapped[RecurringPayment] = relationship(lazy="joined")
    receipt: Mapped["Receipt | None"] = relationship(lazy="selectin", uselist=False, viewonly=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("occurrence_id", "channel", "recipient", "kind", name="uq_delivery_dedup"),
        Index("ix_delivery_status_next", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_occurrences.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default=DeliveryKind.REMINDER.value)
    status: Mapped[DeliveryStatus] = mapped_column(
        _enum(DeliveryStatus, "delivery_status"), default=DeliveryStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_tick_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_tick_ok: Mapped[bool] = mapped_column(Boolean, default=True)


class AppMeta(Base):
    """Служебные отметки (например, что сид уже применён)."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_at", "at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_action", "action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_login: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class TelegramUpdatesOffset(Base):
    """Смещение long polling Telegram: обработанные апдейты не обрабатываются повторно после рестарта."""

    __tablename__ = "telegram_updates_offset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_update_id: Mapped[int] = mapped_column(BigInteger)


class Receipt(Base):
    """Чек к конкретному периоду: ссылка и/или файл (png/jpg/pdf). Один чек на период."""

    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("occurrence_id", name="uq_receipt_occurrence"),
        CheckConstraint("url IS NOT NULL OR file_path IS NOT NULL", name="ck_receipt_not_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_occurrences.id", ondelete="CASCADE"))
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fiscal_sign: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # fn:i:fp из QR чека
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Budget(TimestampMixin, Base):
    """Плановая сумма расходов на месяц или год, отдельно по каждой валюте."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "period_type", "year", "month", "currency",
            name="uq_budget_period_currency",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "(period_type = 'month' AND month BETWEEN 1 AND 12) OR (period_type = 'year' AND month IS NULL)",
            name="ck_budget_month",
        ),
        CheckConstraint("planned_amount >= 0", name="ck_budget_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    period_type: Mapped[BudgetPeriod] = mapped_column(_enum(BudgetPeriod, "budget_period"))
    year: Mapped[int] = mapped_column(SmallInteger)
    month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    currency: Mapped[Currency] = mapped_column(_enum(Currency, "currency"))
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class WebhookEndpoint(TimestampMixin, Base):
    """Адрес для вебхуков. Доставки идут через notification_deliveries (channel='webhook', recipient=id)."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    events: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class TelegramLinkCode(Base):
    """Одноразовый код привязки: пользователя (deep link /start) или чата для напоминаний (/bind)."""

    __tablename__ = "telegram_link_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16))  # user | chat
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramPending(Base):
    """Короткое состояние диалога в личке (например, ждём код приглашения)."""

    __tablename__ = "telegram_pending"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    action: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
