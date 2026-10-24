from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.repositories.payments import OccurrenceFilter
from app.schemas.payments import CalendarDayOut, CalendarOut, CurrencySummaryOut, MoneyBucket, OccurrenceOut, SummaryOut
from app.services.summary import CurrencySummary, SummaryService

router = APIRouter(prefix="/payments", tags=["payments"])


def _bucket(b) -> MoneyBucket:
    return MoneyBucket(amount=f"{b.amount:.2f}", count=b.count)


def _currency(cs: CurrencySummary) -> CurrencySummaryOut:
    return CurrencySummaryOut(
        currency=cs.currency,
        total=_bucket(cs.total),
        paid=_bucket(cs.paid),
        unpaid=_bucket(cs.unpaid),
        overdue=_bucket(cs.overdue),
        upcoming=_bucket(cs.upcoming),
    )


@router.get(
    "/summary",
    response_model=SummaryOut,
    summary="Итоги по валютам (без конвертации), в том числе на дату",
    description="`as_of` — дата, на которую считаются итоги: оплачено (`paid_date ≤ as_of`), просрочено на эту дату, "
    "предстоит. По умолчанию — сегодня в APP_TIMEZONE.",
    responses=responses(401, 422),
)
def summary(
    user: UserDep,
    c: ContainerDep,
    db: DbDep,
    from_: date | None = Query(None, alias="from", description="Срок периода не раньше"),
    to: date | None = Query(None, description="Срок периода не позже"),
    as_of: date | None = Query(None, description="Итоги на дату (YYYY-MM-DD)"),
) -> SummaryOut:
    s = SummaryService(db, c.clock).summary(
        OccurrenceFilter(date_from=from_, date_to=to, team_id=user.team_id), as_of=as_of
    )
    return SummaryOut(as_of=s.as_of, currencies=[_currency(cs) for cs in s.currencies])


@router.get(
    "/calendar",
    response_model=CalendarOut,
    summary="Календарь оплат: периоды по дням со статусами и суммами по валютам",
    description="Диапазон не больше 92 дней. В ответ попадают только дни, на которые есть периоды.",
    responses=responses(401, 422),
)
def calendar(
    user: UserDep,
    c: ContainerDep,
    db: DbDep,
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
) -> CalendarOut:
    today = c.clock.today()
    days = SummaryService(db, c.clock).calendar(from_, to, team_id=user.team_id)
    return CalendarOut(
        date_from=from_,
        to=to,
        today=today,
        days=[
            CalendarDayOut(
                date=d.day,
                occurrences=[OccurrenceOut.build(o, today) for o in d.occurrences],
                totals=[_currency(t) for t in d.totals],
            )
            for d in days
        ],
    )
