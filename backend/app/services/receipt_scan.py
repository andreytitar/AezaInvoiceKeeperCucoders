"""Чек с QR-кодом → оплата отмечена сама.

Фото или PDF кассового чека: читаем QR (формат ФНС), берём сумму и дату, ищем неоплаченный период в рублях
с такой же суммой и ближайшим к дате чека сроком (±60 дней), отмечаем оплату датой из чека и прикрепляем
сам чек. Повторно тот же чек (fn+i+fp) не засчитывается.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import ValidationError
from app.domain.fiscal_qr import OPERATION_NAMES, FiscalReceipt, parse_fiscal_qr
from app.domain.money import Currency, format_amount
from app.domain.status import PaymentStatus
from app.infrastructure.qr_reader import read_qr_codes
from app.infrastructure.storage import sniff
from app.models import PaymentOccurrence, Receipt, User
from app.services.occurrences import OccurrenceService
from app.services.receipts import PayloadTooLarge, ReceiptService

MATCH_WINDOW = timedelta(days=60)


@dataclass
class ScanResult:
    status: str  # matched | already_counted | no_match | not_receipt
    message: str
    receipt: FiscalReceipt | None = None
    occurrence: PaymentOccurrence | None = None


class ReceiptScanService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings

    def _find(self, r: FiscalReceipt) -> PaymentOccurrence | None:
        candidates = self.db.scalars(
            select(PaymentOccurrence).where(
                PaymentOccurrence.is_paid.is_(False),
                PaymentOccurrence.currency_snapshot == Currency.RUB,
                PaymentOccurrence.amount_snapshot == r.amount,
                PaymentOccurrence.due_date >= r.day - MATCH_WINDOW,
                PaymentOccurrence.due_date <= r.day + MATCH_WINDOW,
            )
        ).all()
        if not candidates:
            return None
        return min(candidates, key=lambda o: (abs((o.due_date - r.day).days), o.due_date))

    def scan(self, data: bytes, file_name: str | None, actor: User | None) -> ScanResult:
        if len(data) > self.settings.receipt_max_bytes:
            raise PayloadTooLarge("Файл больше 5 МБ")
        if sniff(data) is None:
            raise ValidationError("Нужно фото (PNG/JPG) или PDF чека", details={"field": "file"})
        receipts = [r for r in (parse_fiscal_qr(t) for t in read_qr_codes(data)) if r]
        if not receipts:
            return ScanResult("not_receipt", "На изображении не найден QR-код кассового чека. Сфотографируйте QR крупнее.")
        r = receipts[0]
        amount = format_amount(r.amount, Currency.RUB)
        if not r.is_payment:
            return ScanResult("no_match", f"Это чек «{OPERATION_NAMES.get(r.operation, r.operation)}», а не оплата.", r)
        dup = self.db.scalar(select(Receipt).where(Receipt.fiscal_sign == r.fingerprint))
        if dup is not None:
            occ = self.db.get(PaymentOccurrence, dup.occurrence_id)
            return ScanResult("already_counted", f"Этот чек уже учтён: «{occ.title_snapshot}», срок {occ.due_date:%d.%m.%Y}.", r, occ)
        occ = self._find(r)
        if occ is None:
            return ScanResult(
                "no_match",
                f"Чек на {amount} от {r.day:%d.%m.%Y}: не нашёл неоплаченный платёж на эту сумму в рублях (±60 дней).",
                r,
            )
        paid_date = min(r.day, self.clock.today())
        occ = OccurrenceService(self.db, self.clock, self.settings).mark(
            occ.id, status=PaymentStatus.PAID, paid_date=paid_date, paid_date_provided=True, actor=actor
        )
        ReceiptService(self.db, self.clock, self.settings).upsert(
            occ.id,
            url=None,
            file_bytes=data,
            file_name=file_name or f"чек {r.day:%d.%m.%Y}.{sniff(data)[1]}",
            actor=actor,
            fiscal_sign=r.fingerprint,
        )
        self.db.refresh(occ, ["receipt"])
        late = (paid_date - occ.due_date).days
        tail = f", с опозданием {late} дн." if late > 0 else ", в срок"
        return ScanResult(
            "matched",
            f"Оплата отмечена: «{occ.title_snapshot}» — {amount}, срок {occ.due_date:%d.%m.%Y}, "
            f"оплачено {paid_date:%d.%m.%Y}{tail}. Чек прикреплён.",
            r,
            occ,
        )
