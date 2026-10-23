from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import OutputModel


class ReceiptOut(OutputModel):
    occurrence_id: uuid.UUID
    url: str | None
    file_name: str | None
    mime: str | None
    size: int | None
    file_url: str | None
    updated_at: datetime

    @classmethod
    def build(cls, r) -> ReceiptOut:
        return cls(
            occurrence_id=r.occurrence_id,
            url=r.url,
            file_name=r.file_name,
            mime=r.mime,
            size=r.size,
            file_url=f"/api/v1/payment-occurrences/{r.occurrence_id}/receipt/file" if r.file_path else None,
            updated_at=r.updated_at,
        )
