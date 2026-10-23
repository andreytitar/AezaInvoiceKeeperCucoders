from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Query, Response, status

from app.api.deps import AdminDep, ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.schemas.payments import RecurringPaymentCreate, RecurringPaymentOut
from app.services.payments import PaymentService

router = APIRouter(prefix="/recurring-payments", tags=["recurring-payments"])


@router.get("", response_model=list[RecurringPaymentOut], summary="Список регулярных платежей", responses=responses(401))
def list_payments(
    _: UserDep,
    c: ContainerDep,
    db: DbDep,
    include_deleted: bool = Query(False, description="Показать и прекращённые платежи"),
) -> list[RecurringPaymentOut]:
    svc = PaymentService(db, c.clock, c.settings)
    payments = svc.list(include_deleted)
    next_due = svc.next_due_dates([p.id for p in payments])
    return [RecurringPaymentOut.build(p, next_due[p.id]) for p in payments]


@router.post(
    "",
    response_model=RecurringPaymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать регулярный платёж (admin)",
    description="Создаёт первый и следующий периоды. Если до срока ≤ REMINDER_DAYS_BEFORE дней, "
    "напоминание отправляется сразу.",
    responses=responses(401, 403, 422),
)
def create_payment(
    body: RecurringPaymentCreate, admin: AdminDep, c: ContainerDep, db: DbDep, background: BackgroundTasks
) -> RecurringPaymentOut:
    svc = PaymentService(db, c.clock, c.settings)
    payment = svc.create(**body.model_dump(), actor=admin)
    kick = c.extras.get("kick_dispatch")
    if kick:
        background.add_task(kick)
    return RecurringPaymentOut.build(payment, svc.next_due_dates([payment.id])[payment.id])


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Прекратить платёж (admin): история сохраняется, напоминаний больше нет",
    description="Soft delete. Будущие неоплаченные периоды удаляются, прошлые и оплаченные остаются "
    "с признаком `recurring_payment_deleted`. Повторный DELETE возвращает 404.",
    responses=responses(401, 403, 404),
)
def delete_payment(payment_id: uuid.UUID, _: AdminDep, c: ContainerDep, db: DbDep) -> Response:
    PaymentService(db, c.clock, c.settings).delete(payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
