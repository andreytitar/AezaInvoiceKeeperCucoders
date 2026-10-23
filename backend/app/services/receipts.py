"""Чеки к периодам. Права как у отметки оплаты (любой авторизованный пользователь)."""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import DomainError, NotFound, ValidationError
from app.infrastructure.storage import LocalStorage, sniff
from app.models import Receipt, User
from app.repositories.payments import OccurrenceRepository
from app.services.audit import AuditService


class PayloadTooLarge(DomainError):
    code = "payload_too_large"
    http_status = 413


def validate_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(url) > 2000:
        raise ValidationError("Ссылка должна начинаться с http:// или https://", details={"field": "url"})
    return url


def _snapshot(r: Receipt) -> dict:
    return {"url": r.url, "file_name": r.file_name, "mime": r.mime, "size": r.size}


class ReceiptService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings, storage: LocalStorage | None = None) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.storage = storage or LocalStorage(settings.uploads_dir)
        self.occurrences = OccurrenceRepository(db)

    def _occurrence(self, occurrence_id: uuid.UUID):
        occ = self.occurrences.get(occurrence_id)
        if occ is None:
            raise NotFound("Период не найден")
        return occ

    def get(self, occurrence_id: uuid.UUID) -> Receipt:
        self._occurrence(occurrence_id)
        r = self.db.scalar(select(Receipt).where(Receipt.occurrence_id == occurrence_id))
        if r is None:
            raise NotFound("Чек не прикреплён")
        return r

    def upsert(
        self,
        occurrence_id: uuid.UUID,
        *,
        url: str | None,
        file_bytes: bytes | None,
        file_name: str | None,
        actor: User | None,
    ) -> Receipt:
        self._occurrence(occurrence_id)
        if not url and file_bytes is None:
            raise ValidationError("Передайте ссылку и/или файл", details={"fields": ["url", "file"]})
        new_file = None
        if file_bytes is not None:
            if len(file_bytes) > self.settings.receipt_max_bytes:
                raise PayloadTooLarge("Файл больше 5 МБ")
            kind = sniff(file_bytes)
            if kind is None:
                raise ValidationError("Разрешены только PNG, JPG и PDF", details={"field": "file"})
            new_file = kind
        url = validate_url(url) if url else None

        r = self.db.scalar(select(Receipt).where(Receipt.occurrence_id == occurrence_id).with_for_update())
        before = _snapshot(r) if r else None
        old_file = None
        if r is None:
            r = Receipt(occurrence_id=occurrence_id)
            self.db.add(r)
        if url:
            r.url = url
        if new_file:
            mime, ext = new_file
            old_file = r.file_path
            r.file_path = self.storage.save(file_bytes or b"", ext)
            r.file_name = (file_name or f"receipt.{ext}")[-255:]
            r.mime = mime
            r.size = len(file_bytes or b"")
        r.uploaded_by = actor.id if actor else None
        AuditService(self.db, self.clock).log(
            "receipt.upsert", entity_type="payment_occurrence", entity_id=occurrence_id,
            before=before, after=_snapshot(r), actor=actor,
        )
        self.db.commit()
        if old_file:
            self.storage.delete(old_file)
        return r

    def delete(self, occurrence_id: uuid.UUID, actor: User | None) -> None:
        r = self.get(occurrence_id)
        file_path = r.file_path
        AuditService(self.db, self.clock).log(
            "receipt.delete", entity_type="payment_occurrence", entity_id=occurrence_id, before=_snapshot(r), actor=actor
        )
        self.db.delete(r)
        self.db.commit()
        if file_path:
            self.storage.delete(file_path)

    def file(self, occurrence_id: uuid.UUID):
        r = self.get(occurrence_id)
        if not r.file_path:
            raise NotFound("К чеку не прикреплён файл")
        path = self.storage.path(r.file_path)
        if not path.exists():
            raise NotFound("Файл чека не найден в хранилище")
        return path, r
