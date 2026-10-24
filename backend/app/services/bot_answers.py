"""Ответы бота на вопросы «что и когда оплатить, что оплачено, что просрочено» (HTML для Telegram)."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.domain.money import Currency, format_amount
from app.domain.status import compute_overdue
from app.models import PaymentOccurrence
from app.repositories.payments import OccurrenceFilter, OccurrenceRepository
from app.services.summary import SummaryService

LIMIT = 15
BUTTONS = 6

BOT_COMMANDS: list[tuple[str, str]] = [
    ("topay", "Что и когда оплатить"),
    ("overdue", "Что просрочено"),
    ("week", "Платежи на ближайшие 7 дней"),
    ("paid", "Что оплачено за 30 дней"),
    ("summary", "Итоги по валютам"),
    ("add", "Добавить платёж (админ)"),
    ("help", "Что умеет бот"),
]

HELP = (
    "<b>Invoice Keeper</b> — напоминания о регулярных платежах.\n\n"
    "/topay — что и когда оплатить\n"
    "/overdue — что просрочено\n"
    "/week — платежи на ближайшие 7 дней\n"
    "/paid — что оплачено за 30 дней\n"
    "/summary — итоги по валютам\n"
    "/add аренда 55000 руб каждое 5-е — добавить платёж (админ)\n\n"
    "Под напоминаниями есть кнопка «Оплачено». В личке можно прислать фото чека с QR-кодом — "
    "бот найдёт платёж и отметит оплату. Можно спрашивать и словами: «что просрочено?»."
)

# вопросы словами (в личке; в группе бот видит только команды)
KEYWORDS = [
    (("просроч", "долг"), "overdue"),
    (("недел", "7 дн"), "week"),
    (("итог", "сколько всего", "сводк"), "summary"),
    (("уже оплач", "оплачено", "заплатили"), "paid"),
    (("оплатить", "заплатить", "платеж", "платёж", "к оплате"), "topay"),
    (("помощ", "help", "что умеешь"), "help"),
]


def command_for_text(text: str) -> str | None:
    t = text.lower()
    for words, cmd in KEYWORDS:
        if any(w in t for w in words):
            return cmd
    return None


@dataclass
class BotAnswer:
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)  # (текст, callback_data)

    def reply_markup(self) -> dict | None:
        if not self.buttons:
            return None
        return {"inline_keyboard": [[{"text": t, "callback_data": d}] for t, d in self.buttons]}


def _money(o: PaymentOccurrence) -> str:
    return html.escape(format_amount(o.amount_snapshot, o.currency_snapshot))


def _totals(items: list[PaymentOccurrence]) -> str:
    sums: dict[Currency, object] = {}
    for o in items:
        sums[o.currency_snapshot] = sums.get(o.currency_snapshot, 0) + o.amount_snapshot
    return " · ".join(html.escape(format_amount(v, c)) for c, v in sums.items()) or "—"


class BotAnswers:
    def __init__(self, db: DbSession, clock: Clock, team_id=None) -> None:
        self.db = db
        self.clock = clock
        self.team_id = team_id
        self.repo = OccurrenceRepository(db)

    def _scope(self, f: OccurrenceFilter) -> OccurrenceFilter:
        f.team_id = self.team_id
        return f

    def _line(self, o: PaymentOccurrence) -> str:
        today = self.clock.today()
        info = compute_overdue(o.due_date, o.is_paid, o.paid_date, today)
        if o.is_paid:
            late = f", с опозданием {info.overdue_days} дн." if info.is_overdue else ""
            tail = f"оплачено {o.paid_date:%d.%m}{late}"
        elif info.is_overdue:
            tail = f"<b>просрочено {info.overdue_days} дн.</b>"
        else:
            d = (o.due_date - today).days
            tail = "сегодня" if d == 0 else "завтра" if d == 1 else f"через {d} дн."
        return f"• {o.due_date:%d.%m} — {html.escape(o.title_snapshot)} — <b>{_money(o)}</b> ({tail})"

    def _list(self, f: OccurrenceFilter, sort: str, title: str, empty: str, buttons: bool) -> BotAnswer:
        items, total = self.repo.query(f, self.clock.today(), sort, 0, LIMIT)
        if not items:
            return BotAnswer(f"<b>{title}</b>\n\n{empty}")
        lines = [f"<b>{title}</b>", ""] + [self._line(o) for o in items]
        if total > LIMIT:
            lines.append(f"… и ещё {total - LIMIT}")
        if not f.status == "paid":
            all_items = self.repo.all_filtered(f, self.clock.today())
            lines += ["", f"Итого: {_totals(all_items)}"]
        btns = []
        if buttons:
            btns = [(f"Оплачено: {o.title_snapshot[:40]} {o.due_date:%d.%m}", f"lp:{o.id}") for o in items[:BUTTONS]]
        return BotAnswer("\n".join(lines), btns)

    def topay(self) -> BotAnswer:
        return self._list(self._scope(OccurrenceFilter(status="unpaid")), "due_date", "Что и когда оплатить", "Всё оплачено.", True)

    def overdue(self) -> BotAnswer:
        return self._list(
            self._scope(OccurrenceFilter(status="unpaid", overdue=True)), "due_date", "Просрочено", "Просрочек нет.", True
        )

    def week(self) -> BotAnswer:
        today = self.clock.today()
        return self._list(
            self._scope(OccurrenceFilter(status="unpaid", overdue=False, date_to=today + timedelta(days=7))),
            "due_date",
            "Ближайшие 7 дней",
            "В ближайшую неделю платежей нет.",
            True,
        )

    def paid(self) -> BotAnswer:
        today = self.clock.today()
        items = [
            o
            for o in self.repo.all_filtered(self._scope(OccurrenceFilter(status="paid")), today)
            if o.paid_date and o.paid_date >= today - timedelta(days=30)
        ]
        items.sort(key=lambda o: o.paid_date, reverse=True)
        if not items:
            return BotAnswer("<b>Оплачено за 30 дней</b>\n\nОплат не было.")
        lines = ["<b>Оплачено за 30 дней</b>", ""] + [self._line(o) for o in items[:LIMIT]]
        lines += ["", f"Итого: {_totals(items)}"]
        return BotAnswer("\n".join(lines))

    def summary(self) -> BotAnswer:
        s = SummaryService(self.db, self.clock).summary(self._scope(OccurrenceFilter()))
        lines = [f"<b>Итоги на {s.as_of:%d.%m.%Y}</b>", ""]
        for c in s.currencies:
            if not c.total.count:
                continue
            f = lambda v: html.escape(format_amount(v, c.currency))  # noqa: E731
            lines.append(
                f"<b>{c.currency.value}</b>: к оплате {f(c.unpaid.amount)} ({c.unpaid.count}), "
                f"просрочено {f(c.overdue.amount)} ({c.overdue.count}), оплачено {f(c.paid.amount)} ({c.paid.count})"
            )
        if len(lines) == 2:
            lines.append("Платежей пока нет.")
        return BotAnswer("\n".join(lines))

    def weekly_digest(self) -> BotAnswer:
        overdue, week = self.overdue(), self.week()
        return BotAnswer(f"<b>Сводка на неделю</b>\n\n{overdue.text}\n\n{week.text}", (overdue.buttons + week.buttons)[:BUTTONS])
