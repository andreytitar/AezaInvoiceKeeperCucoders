from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Query

from app.api.deps import AdminDep, ContainerDep, DbDep
from app.api.errors import responses
from app.repositories.audit import AuditFilter, AuditRepository
from app.schemas.audit import AuditLogOut, AuditLogPage

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get(
    "",
    response_model=AuditLogPage,
    summary="Журнал действий (admin)",
    description="Вход/выход, платежи, отметки оплаты, пользователи, отправки уведомлений. Новые записи сверху.",
    responses=responses(401, 403, 422),
)
def list_audit_logs(
    _: AdminDep,
    c: ContainerDep,
    db: DbDep,
    action: str | None = Query(None, max_length=64, description="Префикс действия, например `occurrence.` или `auth.login`"),
    entity_type: str | None = Query(None, max_length=32),
    entity_id: str | None = Query(None, max_length=64),
    actor_login: str | None = Query(None, max_length=64),
    from_: date | None = Query(None, alias="from", description="С даты (в APP_TIMEZONE)"),
    to: date | None = Query(None, description="По дату включительно (в APP_TIMEZONE)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AuditLogPage:
    tz = c.settings.tz
    f = AuditFilter(
        action=action or None,
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        actor_login=actor_login or None,
        since=datetime.combine(from_, time.min, tz) if from_ else None,
        until=datetime.combine(to + timedelta(days=1), time.min, tz) if to else None,
    )
    items, total = AuditRepository(db).query(f, (page - 1) * page_size, page_size)
    return AuditLogPage(
        items=[AuditLogOut.model_validate(i) for i in items], total=total, page=page, page_size=page_size
    )
