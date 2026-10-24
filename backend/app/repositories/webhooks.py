from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import NotificationDelivery, WebhookEndpoint


class WebhookRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def list(self, team_id: uuid.UUID | None = None) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpoint).order_by(WebhookEndpoint.created_at)
        if team_id is not None:
            stmt = stmt.where(WebhookEndpoint.team_id == team_id)
        return list(self.db.scalars(stmt))

    def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint | None:
        return self.db.get(WebhookEndpoint, endpoint_id)

    def add(self, ep: WebhookEndpoint) -> WebhookEndpoint:
        self.db.add(ep)
        self.db.flush()
        return ep

    def subscribed(self, event: str, team_id: uuid.UUID | None = None) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True), WebhookEndpoint.events.any(event))
        if team_id is not None:
            stmt = stmt.where(WebhookEndpoint.team_id == team_id)
        return list(self.db.scalars(stmt))

    def deliveries(self, endpoint_id: uuid.UUID, offset: int, limit: int) -> tuple[list[NotificationDelivery], int]:
        stmt = select(NotificationDelivery).where(
            NotificationDelivery.channel == "webhook", NotificationDelivery.recipient == str(endpoint_id)
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(self.db.scalars(stmt.order_by(NotificationDelivery.created_at.desc()).offset(offset).limit(limit)))
        return items, total
