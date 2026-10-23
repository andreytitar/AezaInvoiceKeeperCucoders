from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.domain.money import Currency
from app.domain.status import PaymentStatus
from app.repositories.payments import OccurrenceFilter
from app.schemas.payments import OccurrenceOut, OccurrencePage, OccurrencePatch, OccurrenceSort
from app.services.occurrences import OccurrenceService

router = APIRouter(prefix="/payment-occurrences", tags=["payment-occurrences"])


@router.get("", response_model=OccurrencePage, summary="Периоды платежей с фильтрами", responses=responses(401, 422))
def list_occurrences(
    _: UserDep,
    c: ContainerDep,
    db: DbDep,
    status: PaymentStatus | None = Query(None, description="paid | unpaid"),
    overdue: bool | None = Query(None, description="Только просроченные (true) / без просрочки (false)"),
    currency: Currency | None = None,
    from_: date | None = Query(None, alias="from", description="Срок не раньше (YYYY-MM-DD)"),
    to: date | None = Query(None, description="Срок не позже (YYYY-MM-DD)"),
    recurring_payment_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100, description="Поиск по названию"),
    sort: OccurrenceSort = "due_date",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> OccurrencePage:
    f = OccurrenceFilter(
        status=status.value if status else None,
        overdue=overdue,
        currency=currency,
        date_from=from_,
        date_to=to,
        recurring_payment_id=recurring_payment_id,
        search=q or None,
    )
    result = OccurrenceService(db, c.clock, c.settings).list(f, sort, page, page_size)
    today = c.clock.today()
    return OccurrencePage(
        items=[OccurrenceOut.build(o, today) for o in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{occurrence_id}", response_model=OccurrenceOut, summary="Период", responses=responses(401, 404))
def get_occurrence(occurrence_id: uuid.UUID, _: UserDep, c: ContainerDep, db: DbDep) -> OccurrenceOut:
    return OccurrenceOut.build(OccurrenceService(db, c.clock, c.settings).get(occurrence_id), c.clock.today())


@router.patch(
    "/{occurrence_id}",
    response_model=OccurrenceOut,
    summary="Отметить оплату / отменить / исправить фактическую дату",
    description="`{\"status\": \"paid\", \"paid_date\": \"2026-10-20\"}` — оплачено (дата по умолчанию — сегодня). "
    "`{\"status\": \"unpaid\"}` — отмена, фактическая дата очищается. Срок (`due_date`) не меняется.",
    responses=responses(401, 404, 422),
)
def patch_occurrence(
    occurrence_id: uuid.UUID, body: OccurrencePatch, user: UserDep, c: ContainerDep, db: DbDep
) -> OccurrenceOut:
    occ = OccurrenceService(db, c.clock, c.settings).mark(
        occurrence_id,
        status=body.status,
        paid_date=body.paid_date,
        paid_date_provided="paid_date" in body.model_fields_set,
        actor=user,
    )
    return OccurrenceOut.build(occ, c.clock.today())
