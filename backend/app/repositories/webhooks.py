from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import NotificationDelivery, WebhookEndpoint


class WebhookRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def list(self) -> list[WebhookEndpoint]:
        return list(self.db.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at)))

    def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint | None:
        return self.db.get(WebhookEndpoint, endpoint_id)

    def add(self, ep: WebhookEndpoint) -> WebhookEndpoint:
        self.db.add(ep)
        self.db.flush()
        return ep

    def subscribed(self, event: str) -> list[WebhookEndpoint]:
        return list(
            self.db.scalars(
                select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True), WebhookEndpoint.events.any(event))
            )
        )

    def deliveries(self, endpoint_id: uuid.UUID, offset: int, limit: int) -> tuple[list[NotificationDelivery], int]:
        stmt = select(NotificationDelivery).where(
            NotificationDelivery.channel == "webhook", NotificationDelivery.recipient == str(endpoint_id)
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(self.db.scalars(stmt.order_by(NotificationDelivery.created_at.desc()).offset(offset).limit(limit)))
        return items, total
