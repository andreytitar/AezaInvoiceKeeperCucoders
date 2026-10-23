from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.repositories.payments import OccurrenceFilter
from app.schemas.payments import CurrencySummaryOut, MoneyBucket, SummaryOut
from app.services.summary import SummaryService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get(
    "/summary",
    response_model=SummaryOut,
    summary="Итоги по валютам (без конвертации)",
    responses=responses(401, 422),
)
def summary(
    _: UserDep,
    c: ContainerDep,
    db: DbDep,
    from_: date | None = Query(None, alias="from", description="Срок периода не раньше"),
    to: date | None = Query(None, description="Срок периода не позже"),
) -> SummaryOut:
    s = SummaryService(db, c.clock).summary(OccurrenceFilter(date_from=from_, date_to=to))
    return SummaryOut(
        as_of=s.as_of,
        currencies=[
            CurrencySummaryOut(
                currency=cs.currency,
                total=MoneyBucket(amount=f"{cs.total.amount:.2f}", count=cs.total.count),
                paid=MoneyBucket(amount=f"{cs.paid.amount:.2f}", count=cs.paid.count),
                unpaid=MoneyBucket(amount=f"{cs.unpaid.amount:.2f}", count=cs.unpaid.count),
                overdue=MoneyBucket(amount=f"{cs.overdue.amount:.2f}", count=cs.overdue.count),
            )
            for cs in s.currencies
        ],
    )
