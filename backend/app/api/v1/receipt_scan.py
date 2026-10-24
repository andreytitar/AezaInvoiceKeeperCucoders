from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.schemas.payments import OccurrenceOut
from app.services.receipt_scan import ReceiptScanService

router = APIRouter(prefix="/receipts", tags=["receipts"])


class FiscalOut(BaseModel):
    date: date
    amount: Decimal
    operation: int


class ScanOut(BaseModel):
    status: Literal["matched", "already_counted", "no_match", "not_receipt"]
    message: str
    receipt: FiscalOut | None
    occurrence: OccurrenceOut | None


@router.post(
    "/scan",
    response_model=ScanOut,
    summary="Распознать кассовый чек по QR и отметить оплату",
    description="Фото (PNG/JPG) или PDF чека до 5 МБ. Из QR-кода (формат ФНС) берутся сумма и дата; находится "
    "неоплаченный период в рублях с этой суммой и ближайшим сроком (±60 дней), он отмечается оплаченным датой "
    "чека, чек прикрепляется. Повторно тот же чек не засчитывается.",
    responses={**responses(401, 422), 413: {"description": "Файл больше 5 МБ"}},
)
async def scan_receipt(
    file: Annotated[UploadFile, File()], user: UserDep, c: ContainerDep, db: DbDep
) -> ScanOut:
    data = await file.read(c.settings.receipt_max_bytes + 1)
    res = ReceiptScanService(db, c.clock, c.settings).scan(data, file.filename, user)
    return ScanOut(
        status=res.status,
        message=res.message,
        receipt=FiscalOut(date=res.receipt.day, amount=res.receipt.amount, operation=res.receipt.operation) if res.receipt else None,
        occurrence=OccurrenceOut.build(res.occurrence, c.clock.today()) if res.occurrence else None,
    )
