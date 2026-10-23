from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import AuditLog


@dataclass
class AuditFilter:
    action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    actor_login: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class AuditRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def add(self, entry: AuditLog) -> None:
        self.db.add(entry)

    def query(self, f: AuditFilter, offset: int, limit: int) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        if f.action:
            stmt = stmt.where(AuditLog.action.startswith(f.action))
        if f.entity_type:
            stmt = stmt.where(AuditLog.entity_type == f.entity_type)
        if f.entity_id:
            stmt = stmt.where(AuditLog.entity_id == f.entity_id)
        if f.actor_login:
            stmt = stmt.where(func.lower(AuditLog.actor_login) == f.actor_login.lower())
        if f.since:
            stmt = stmt.where(AuditLog.at >= f.since)
        if f.until:
            stmt = stmt.where(AuditLog.at < f.until)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(self.db.scalars(stmt.order_by(AuditLog.at.desc(), AuditLog.seq.desc()).offset(offset).limit(limit)))
        return items, total
