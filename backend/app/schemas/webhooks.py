from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models import DeliveryStatus
from app.schemas.common import InputModel, OutputModel

Event = Literal["payment.reminder", "payment.paid", "payment.unpaid", "payment.overdue"]


class WebhookCreate(InputModel):
    url: str = Field(max_length=2000, examples=["https://example.com/hooks/invoice-keeper"])
    events: list[Event] = Field(min_length=1, examples=[["payment.reminder", "payment.paid", "payment.unpaid", "payment.overdue"]])
    secret: str | None = Field(default=None, min_length=8, max_length=200, description="Секрет для подписи HMAC-SHA256; хранится зашифрованным и не возвращается")
    is_active: bool = True
    description: str | None = Field(default=None, max_length=200)


class WebhookUpdate(InputModel):
    url: str | None = Field(default=None, max_length=2000)
    events: list[Event] | None = Field(default=None, min_length=1)
    secret: str | None = Field(default=None, max_length=200, description="Пустая строка или null — убрать секрет")
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=200)


class WebhookOut(OutputModel):
    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    description: str | None
    has_secret: bool
    created_at: datetime

    @classmethod
    def build(cls, ep) -> WebhookOut:
        return cls(id=ep.id, url=ep.url, events=list(ep.events), is_active=ep.is_active, description=ep.description,
                   has_secret=ep.secret_enc is not None, created_at=ep.created_at)


class WebhookDeliveryOut(OutputModel):
    id: uuid.UUID
    occurrence_id: uuid.UUID
    event: str
    status: DeliveryStatus
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    sent_at: datetime | None
    response: str | None
    created_at: datetime


class WebhookDeliveryPage(OutputModel):
    items: list[WebhookDeliveryOut]
    total: int
    page: int
    page_size: int


class WebhookTestResult(OutputModel):
    ok: bool
    detail: str | None
