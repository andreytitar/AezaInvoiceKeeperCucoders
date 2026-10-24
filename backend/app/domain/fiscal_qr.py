"""Разбор QR-кода российского кассового чека (формат ФНС): t=20261020T1530&s=55000.00&fn=…&i=…&fp=…&n=1.

t — дата и время, s — сумма в рублях, fn/i/fp — номер ФН, документа и фискальный признак,
n — тип операции (1 — приход, 2 — возврат прихода, 3 — расход, 4 — возврат расхода).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs

OPERATION_NAMES = {1: "приход", 2: "возврат прихода", 3: "расход", 4: "возврат расхода"}


@dataclass(frozen=True)
class FiscalReceipt:
    when: datetime
    amount: Decimal
    fn: str
    i: str
    fp: str
    operation: int

    @property
    def day(self) -> date:
        return self.when.date()

    @property
    def is_payment(self) -> bool:
        return self.operation in (1, 3)

    @property
    def fingerprint(self) -> str:
        return f"{self.fn}:{self.i}:{self.fp}"


def parse_fiscal_qr(text: str) -> FiscalReceipt | None:
    """FiscalReceipt или None, если строка не похожа на QR кассового чека."""
    q = {k.lower(): v[0] for k, v in parse_qs(text.strip(), keep_blank_values=True).items()}
    if not {"t", "s", "fn", "i", "fp"} <= q.keys():
        return None
    t = q["t"]
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            when = datetime.strptime(t, fmt)
            break
        except ValueError:
            continue
    else:
        return None
    try:
        amount = Decimal(q["s"].replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    try:
        op = int(q.get("n") or 1)
    except ValueError:
        op = 1
    return FiscalReceipt(when=when, amount=amount.quantize(Decimal("0.01")), fn=q["fn"], i=q["i"], fp=q["fp"], operation=op)
