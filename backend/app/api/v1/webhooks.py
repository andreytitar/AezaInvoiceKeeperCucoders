from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminDep, ContainerDep, DbDep
from app.api.errors import responses
from app.infrastructure.channels.webhook import event_name
from app.schemas.webhooks import (
    WebhookCreate,
    WebhookDeliveryOut,
    WebhookDeliveryPage,
    WebhookOut,
    WebhookTestResult,
    WebhookUpdate,
)
from app.services.webhooks import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
R = responses(401, 403, 404, 422)


@router.get("", response_model=list[WebhookOut], summary="Адреса вебхуков (admin)", responses=responses(401, 403))
def list_webhooks(_: AdminDep, c: ContainerDep, db: DbDep) -> list[WebhookOut]:
    return [WebhookOut.build(e) for e in WebhookService(db, c.clock, c.settings).list()]


@router.post(
    "",
    response_model=WebhookOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить адрес (admin)",
    description="События: payment.reminder, payment.paid, payment.unpaid, payment.overdue. Тело — JSON со "
    "`schema_version`, подпись `X-InvoiceKeeper-Signature: sha256=HMAC(secret, timestamp + '.' + body)`, ключ "
    "идемпотентности в `Idempotency-Key`. Внутренние адреса запрещены, пока WEBHOOK_ALLOW_PRIVATE=false.",
    responses=responses(401, 403, 422),
)
def create_webhook(body: WebhookCreate, admin: AdminDep, c: ContainerDep, db: DbDep) -> WebhookOut:
    ep = WebhookService(db, c.clock, c.settings).create(**body.model_dump(), actor=admin)
    return WebhookOut.build(ep)


@router.patch("/{webhook_id}", response_model=WebhookOut, summary="Изменить адрес (admin)", responses=R)
def update_webhook(webhook_id: uuid.UUID, body: WebhookUpdate, admin: AdminDep, c: ContainerDep, db: DbDep) -> WebhookOut:
    fields = body.model_dump(exclude_unset=True)
    for key in ("url", "events", "is_active"):
        if key in fields and fields[key] is None:
            fields.pop(key)
    return WebhookOut.build(WebhookService(db, c.clock, c.settings).update(webhook_id, fields, actor=admin))


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить адрес (admin)",
               responses=responses(401, 403, 404))
def delete_webhook(webhook_id: uuid.UUID, admin: AdminDep, c: ContainerDep, db: DbDep) -> Response:
    WebhookService(db, c.clock, c.settings).delete(webhook_id, actor=admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryPage, summary="Журнал доставок (admin)", responses=R)
def webhook_deliveries(
    webhook_id: uuid.UUID, _: AdminDep, c: ContainerDep, db: DbDep,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
) -> WebhookDeliveryPage:
    items, total = WebhookService(db, c.clock, c.settings).deliveries(webhook_id, page, page_size)
    return WebhookDeliveryPage(
        items=[
            WebhookDeliveryOut(
                id=d.id, occurrence_id=d.occurrence_id, event=event_name(d.kind), status=d.status, attempts=d.attempts,
                next_attempt_at=d.next_attempt_at, last_error=d.last_error, sent_at=d.sent_at, response=d.external_id,
                created_at=d.created_at,
            )
            for d in items
        ],
        total=total, page=page, page_size=page_size,
    )


@router.post("/{webhook_id}/test", response_model=WebhookTestResult, summary="Отправить тестовое событие (admin)", responses=R)
async def test_webhook(webhook_id: uuid.UUID, _: AdminDep, c: ContainerDep, db: DbDep) -> WebhookTestResult:
    result = await WebhookService(db, c.clock, c.settings).ping(webhook_id)
    return WebhookTestResult(ok=result.ok, detail=result.external_id if result.ok else result.error)
