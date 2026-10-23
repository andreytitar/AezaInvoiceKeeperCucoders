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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.money import Currency
from app.domain.schedule import Recurrence


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


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


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_login_alive", "login", unique=True, postgresql_where=text("deleted_at IS NULL")),
        Index(
            "uq_users_telegram_alive",
            "telegram_user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND telegram_user_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.USER)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
