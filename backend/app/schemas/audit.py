from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import OutputModel


class AuditLogOut(OutputModel):
    id: uuid.UUID
    at: datetime
    actor_user_id: uuid.UUID | None
    actor_login: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    user_agent: str | None


class AuditLogPage(OutputModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
