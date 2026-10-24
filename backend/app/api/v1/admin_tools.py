from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AdminDep, ContainerDep
from app.api.errors import responses
from app.services.audit import AuditService
from app.services.scheduler import run_checks

router = APIRouter(prefix="/admin", tags=["admin"])


class CheckResult(BaseModel):
    periods_created: int
    reminders_queued: int
    overdue_events_queued: int
    sent: int
    failed: int
    dead: int
    cancelled: int


@router.post(
    "/run-checks",
    response_model=CheckResult,
    summary="Проверить сейчас (admin): генерация периодов, напоминания, доставка",
    description="То же, что делает worker раз в минуту. Идемпотентно и безопасно параллельно с worker.",
    responses=responses(401, 403),
)
async def run_checks_now(admin: AdminDep, c: ContainerDep) -> CheckResult:
    stats = await run_checks(c)
    with c.session_factory() as db:
        AuditService(db, c.clock).log("admin.run_checks", after=stats.as_dict(), actor=admin)
        db.commit()
    return CheckResult(**stats.as_dict())
