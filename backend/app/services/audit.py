"""Журнал действий. Вызывается из сервисов (не из роутеров), пишет в той же транзакции, что и изменение.
Пароли и токены сюда никогда не попадают."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.infrastructure.request_context import current
from app.models import AuditLog, User
from app.repositories.audit import AuditRepository

SYSTEM_ACTOR = "system"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


class AuditService:
    def __init__(self, db: DbSession, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.repo = AuditRepository(db)

    def log(
        self,
        action: str,
        *,
        entity_type: str | None = None,
        entity_id: Any = None,
        before: dict | None = None,
        after: dict | None = None,
        actor: User | None = None,
        actor_login: str | None = None,
        team_id: uuid.UUID | None = None,
    ) -> None:
        ctx = current()
        if team_id is None and actor is not None:
            team_id = actor.team_id
        self.repo.add(
            AuditLog(
                at=self.clock.now(),
                team_id=team_id,
                actor_user_id=actor.id if actor else ctx.actor_id,
                actor_login=(actor.login if actor else None) or actor_login or ctx.actor_login or SYSTEM_ACTOR,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                before=_jsonable(before) if before is not None else None,
                after=_jsonable(after) if after is not None else None,
                ip=ctx.ip,
                user_agent=(ctx.user_agent or "")[:512] or None,
            )
        )


def payment_snapshot(p) -> dict:
    return {
        "title": p.title,
        "amount": p.amount,
        "currency": p.currency,
        "recurrence": p.recurrence,
        "first_due_date": p.first_due_date,
        "deleted_at": p.deleted_at,
    }


def occurrence_snapshot(o) -> dict:
    return {"status": "paid" if o.is_paid else "unpaid", "paid_date": o.paid_date, "due_date": o.due_date, "title": o.title_snapshot}


def user_snapshot(u) -> dict:
    return {"login": u.login, "email": u.email, "telegram_user_id": u.telegram_user_id, "role": u.role}
