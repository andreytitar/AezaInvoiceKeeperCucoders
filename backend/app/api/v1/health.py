from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select, text

from app.models import WorkerHeartbeat

router = APIRouter(tags=["health"])


class WorkerHealth(BaseModel):
    last_tick_at: str | None
    alive: bool


class HealthResponse(BaseModel):
    status: str
    db: str
    worker: WorkerHealth
    today: str
    timezone: str
    fake_today: bool


@router.get("/health", response_model=HealthResponse, summary="Состояние сервиса (БД и heartbeat worker)")
def health(request: Request) -> HealthResponse:
    c = request.app.state.container
    db_status = "ok"
    last_tick = None
    try:
        with c.session_factory() as s:
            s.execute(text("SELECT 1"))
            hb = s.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.id == 1))
            last_tick = hb.last_tick_at if hb else None
    except Exception:  # noqa: BLE001
        db_status = "error"
    alive = bool(last_tick and (c.clock.now() - last_tick).total_seconds() < 3 * c.settings.worker_interval_seconds + 30)
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        worker=WorkerHealth(last_tick_at=last_tick.isoformat() if last_tick else None, alive=alive),
        today=c.clock.today().isoformat(),
        timezone=c.settings.app_timezone,
        fake_today=c.settings.app_fake_today is not None,
    )
