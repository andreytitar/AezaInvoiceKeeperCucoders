from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Query, Response, status

from app.api.deps import AdminDep, ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.schemas.payments import RecurringPaymentCreate, RecurringPaymentOut, RecurringPaymentUpdate
from pydantic import Field

from app.domain.phrase import parse_payment_phrase
from app.schemas.common import InputModel
from app.services.payments import PaymentService
from app.services.reminders import dispatch_now

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
    svc = PaymentService(db, c.clock, c.settings, c.channels)
    payment = svc.create(**body.model_dump(), actor=admin)
    background.add_task(dispatch_now, c)
    return RecurringPaymentOut.build(payment, svc.next_due_dates([payment.id])[payment.id])


class ParseRequest(InputModel):
    text: str = Field(min_length=3, max_length=300, examples=["аренда 55000 руб каждое 5-е"])


@router.post(
    "/parse",
    response_model=RecurringPaymentCreate,
    summary="Разобрать фразу в платёж (admin, без сохранения)",
    description="«аренда 55000 руб каждое 5-е», «сервер $25 28 числа», «домен 12 usd ежегодно 01.12». "
    "Возвращает поля для POST /recurring-payments.",
    responses=responses(401, 403, 422),
)
def parse_phrase(body: ParseRequest, _: AdminDep, c: ContainerDep) -> RecurringPaymentCreate:
    p = parse_payment_phrase(body.text, c.clock.today())
    return RecurringPaymentCreate(
        title=p.title, amount=p.amount, currency=p.currency, first_due_date=p.first_due_date, recurrence=p.recurrence
    )


@router.patch(
    "/{payment_id}",
    response_model=RecurringPaymentOut,
    summary="Изменить название, сумму или валюту (admin)",
    description="Оплаченные и прошедшие периоды сохраняют прежние значения (снимки). Неоплаченные периоды "
    "со сроком сегодня и позже получают новые.",
    responses=responses(401, 403, 404, 422),
)
def update_payment(
    payment_id: uuid.UUID, body: RecurringPaymentUpdate, admin: AdminDep, c: ContainerDep, db: DbDep
) -> RecurringPaymentOut:
    svc = PaymentService(db, c.clock, c.settings)
    payment, _ = svc.update(payment_id, body.model_dump(exclude_unset=True), actor=admin)
    return RecurringPaymentOut.build(payment, svc.next_due_dates([payment.id])[payment.id])


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Прекратить платёж (admin): история сохраняется, напоминаний больше нет",
    description="Soft delete. Будущие неоплаченные периоды удаляются, прошлые и оплаченные остаются "
    "с признаком `recurring_payment_deleted`. Повторный DELETE возвращает 404.",
    responses=responses(401, 403, 404),
)
def delete_payment(payment_id: uuid.UUID, admin: AdminDep, c: ContainerDep, db: DbDep) -> Response:
    PaymentService(db, c.clock, c.settings).delete(payment_id, actor=admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
