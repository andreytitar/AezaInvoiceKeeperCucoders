from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminDep, ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.models import BudgetPeriod
from app.schemas.budgets import BudgetOut, BudgetReportOut, BudgetUpsert
from app.services.budgets import BudgetService

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut], summary="Бюджеты (все пользователи)", responses=responses(401, 422))
def list_budgets(
    user: UserDep, c: ContainerDep, db: DbDep,
    period_type: BudgetPeriod | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
) -> list[BudgetOut]:
    return [BudgetOut.build(b) for b in BudgetService(db, c.clock).list(period_type, year, month, team_id=user.team_id)]


@router.put(
    "",
    response_model=BudgetOut,
    summary="Задать или изменить бюджет (admin)",
    description="Уникален по (тип, год, месяц, валюта): повторный PUT меняет плановую сумму.",
    responses=responses(401, 403, 422),
)
def upsert_budget(body: BudgetUpsert, admin: AdminDep, c: ContainerDep, db: DbDep, response: Response) -> BudgetOut:
    b, created = BudgetService(db, c.clock).upsert(**body.model_dump(), actor=admin)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return BudgetOut.build(b)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить бюджет (admin)",
               responses=responses(401, 403, 404))
def delete_budget(budget_id: uuid.UUID, admin: AdminDep, c: ContainerDep, db: DbDep) -> Response:
    BudgetService(db, c.clock).delete(budget_id, actor=admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/report", response_model=BudgetReportOut, summary="План/факт по каждой валюте", responses=responses(401, 422))
def budget_report(
    user: UserDep, c: ContainerDep, db: DbDep,
    period_type: BudgetPeriod = BudgetPeriod.MONTH,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
) -> BudgetReportOut:
    return BudgetReportOut.build(BudgetService(db, c.clock).report(period_type, year, month, team_id=user.team_id))
