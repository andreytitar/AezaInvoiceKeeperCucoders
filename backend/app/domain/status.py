"""Правила статусов и просрочки. Просрочка не хранится, а вычисляется здесь — в одном месте."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.domain.errors import ValidationError


class PaymentStatus(StrEnum):
    PAID = "paid"
    UNPAID = "unpaid"


@dataclass(frozen=True)
class OverdueInfo:
    is_overdue: bool
    overdue_days: int


def compute_overdue(due_date: date, is_paid: bool, paid_date: date | None, today: date) -> OverdueInfo:
    """Просрочка наступает со следующего дня после срока; оплата в день срока — вовремя.

    - не оплачено и today > due_date      -> просрочено на (today - due_date) дней;
    - оплачено и paid_date > due_date     -> оплачено с просрочкой (paid_date - due_date) дней;
    - иначе                                -> без просрочки.
    """
    if is_paid:
        if paid_date is not None and paid_date > due_date:
            return OverdueInfo(True, (paid_date - due_date).days)
        return OverdueInfo(False, 0)
    if today > due_date:
        return OverdueInfo(True, (today - due_date).days)
    return OverdueInfo(False, 0)


@dataclass(frozen=True)
class PaymentMark:
    is_paid: bool
    paid_date: date | None


def apply_status_change(
    *,
    current_is_paid: bool,
    current_paid_date: date | None,
    new_status: PaymentStatus,
    paid_date: date | None,
    paid_date_provided: bool,
    today: date,
) -> PaymentMark:
    """Применяет правила раздела 2.3 и возвращает новое состояние отметки.

    - «Оплачено» без даты: если период уже оплачен — дата сохраняется (идемпотентность),
      иначе подставляется today.
    - Дата не может быть в будущем.
    - «Не оплачено»: дату передавать нельзя, фактическая дата очищается.
    """
    if new_status == PaymentStatus.UNPAID:
        if paid_date_provided and paid_date is not None:
            raise ValidationError(
                "Фактическую дату оплаты можно передать только вместе со статусом «Оплачено»",
                details={"field": "paid_date"},
            )
        return PaymentMark(False, None)

    if paid_date is None:
        if current_is_paid and current_paid_date is not None:
            return PaymentMark(True, current_paid_date)
        paid_date = today
    if paid_date > today:
        raise ValidationError(
            "Фактическая дата оплаты не может быть в будущем",
            details={"field": "paid_date", "today": today.isoformat()},
        )
    return PaymentMark(True, paid_date)
