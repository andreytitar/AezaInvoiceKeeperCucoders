"""Ответы бота: тексты, карточки, клавиатуры (HTML для Telegram)."""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.orm import Session as DbSession

from app.domain.clock import Clock
from app.domain.money import Currency, format_amount
from app.domain.status import compute_overdue
from app.infrastructure.channels.formatting import due_phrase
from app.models import PaymentOccurrence, User
from app.repositories.payments import OccurrenceFilter, OccurrenceRepository
from app.services.bot_list_format import (
    format_money_bot,
    render_grouped_paid_lines,
    render_grouped_payment_lines,
    totals_currency_lines,
    totals_topay_lines,
)
from app.services.summary import SummaryService

LIMIT = 15  # «Оплачено» за 30 дней
LIST_PAGE = 8  # платежей на странице «К оплате»
PAY_BTN_COLS = 4  # «✅ N» в ряд
BUTTONS = 6  # дайджест

ScreenId = Literal["menu", "topay", "overdue", "week", "paid", "summary", "add_hint", "site"]

NAV_MENU = "nav:m"
NAV_CANCEL_ADD = "nav:x"
NAV_NOOP = "nav:noop"

_SCREEN_CODES: dict[ScreenId, str] = {
    "menu": "m",
    "topay": "t",
    "overdue": "o",
    "week": "w",
    "paid": "p",
    "summary": "s",
    "add_hint": "a",
    "site": "g",
}
_CODE_TO_SCREEN = {v: k for k, v in _SCREEN_CODES.items()}


def nav_callback(screen: ScreenId, page: int = 0) -> str:
    code = _SCREEN_CODES[screen]
    if screen in ("menu", "summary", "add_hint", "site"):
        return f"nav:{code}"
    return f"nav:{code}:{page}"


def list_paid_callback(screen: ScreenId, occurrence_id) -> str:
    return f"lp:{_SCREEN_CODES[screen]}:{occurrence_id}"


def parse_nav_callback(data: str) -> tuple[ScreenId, int] | None:
    if not data.startswith("nav:"):
        return None
    rest = data[4:]
    if rest == "m":
        return "menu", 0
    if rest == "s":
        return "summary", 0
    if rest == "a":
        return "add_hint", 0
    if rest == "g":
        return "site", 0
    if rest == "x":
        return "menu", 0
    if ":" in rest:
        code, _, page_s = rest.partition(":")
        if code in _CODE_TO_SCREEN and page_s.isdigit():
            return _CODE_TO_SCREEN[code], int(page_s)
    return None


def parse_list_paid_callback(data: str) -> tuple[ScreenId | None, str]:
    """Возвращает (экран, uuid-часть). Старый формат lp:{uuid} → экран None."""
    if not data.startswith("lp:"):
        return None, ""
    body = data[3:]
    if body and body[0] in _CODE_TO_SCREEN and len(body) > 2 and body[1] == ":":
        code, _, occ_id = body.partition(":")
        return _CODE_TO_SCREEN[code], occ_id
    return None, body


def unpay_callback(screen_code: str, page: int, occurrence_id) -> str:
    return f"unpay:{screen_code}:{page}:{occurrence_id}"


def parse_unpay_callback(data: str) -> tuple[str, int, str] | None:
    if not data.startswith("unpay:"):
        return None
    parts = data.split(":", 3)
    if len(parts) != 4 or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2]), parts[3]


def paid_undo_keyboard(screen: ScreenId, page: int, occurrence_id) -> list[list[tuple[str, str]]]:
    code = _SCREEN_CODES[screen]
    return [[("↩️ Отменить", unpay_callback(code, page, occurrence_id))]]


_LIST_FOOTER: dict[ScreenId, list[tuple[str, str]]] = {
    "topay": [("🔴 Просрочено", nav_callback("overdue", 0)), ("🏠 В меню", NAV_MENU)],
    "overdue": [("💳 К оплате", nav_callback("topay", 0)), ("🏠 В меню", NAV_MENU)],
    "week": [("💳 К оплате", nav_callback("topay", 0)), ("🏠 В меню", NAV_MENU)],
    "paid": [("💳 К оплате", nav_callback("topay", 0)), ("🏠 В меню", NAV_MENU)],
}


def list_screen_keyboard(
    screen: ScreenId,
    items: list[PaymentOccurrence],
    page: int,
    total_pages: int,
    start_number: int,
    *,
    pay_buttons: bool = True,
) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    if pay_buttons:
        pairs: list[tuple[str, str]] = []
        for i, o in enumerate(items):
            n = start_number + i
            pairs.append((f"✅ {n}", list_paid_callback(screen, o.id)))
            if len(pairs) >= PAY_BTN_COLS:
                rows.append(pairs)
                pairs = []
        if pairs:
            rows.append(pairs)
    nav_row: list[tuple[str, str]] = []
    nav_row.append(("◀️", nav_callback(screen, page - 1)) if page > 0 else ("·", NAV_NOOP))
    nav_row.append((f"{page + 1} / {total_pages}", NAV_NOOP))
    nav_row.append(
        ("▶️", nav_callback(screen, page + 1)) if page + 1 < total_pages else ("·", NAV_NOOP)
    )
    rows.append(nav_row)
    rows.append(_LIST_FOOTER.get(screen, [("🏠 В меню", NAV_MENU)]))
    return rows


def screen_from_message_text(text: str) -> ScreenId:
    """Эвристика для старых сообщений с lp:{uuid}."""
    first = text.split("\n", 1)[0] if text else ""
    if "отметил" in text and "Оплачено" in text:
        return "topay"
    if "📅" in first and "На неделю" in first:
        return "week"
    if "🔴" in first and "Просрочено" in first:
        return "overdue"
    if "✅" in first and "Оплачено" in first and "30" in text:
        return "paid"
    if "💳" in first and "К оплате" in first:
        return "topay"
    if "Просрочек нет" in text or (first.startswith("🔴") and "Просрочено" in first):
        return "overdue"
    if "На этой неделе" in text or "На неделю" in first:
        return "week"
    return "topay"


MENU_INTRO = (
    "<b>Invoice Keeper</b>\n"
    "Напоминания о регулярных платежах. Выберите раздел или спросите словами в личке."
)

HELP = (
    f"{MENU_INTRO}\n\n"
    "Команды дублируют кнопки: /topay, /overdue, /week, /paid, /summary.\n"
    "Под напоминаниями — «Оплачено». Админ: /add или кнопка «Добавить платёж»."
)

ADD_USAGE = (
    "<b>Добавить платёж</b>\n"
    "Одной фразой: название, сумма, валюта и день.\n\n"
    "Примеры:\n"
    "• <code>/add аренда 55000 руб каждое 5-е</code>\n"
    "• <code>/add сервер $25 28 числа</code>\n"
    "• <code>/add домен 12 usd ежегодно 01.12</code>"
)

KEYWORDS = [
    (("просроч", "долг"), "overdue"),
    (("недел", "7 дн"), "week"),
    (("итог", "сколько всего", "сводк"), "summary"),
    (("уже оплач", "оплачено", "заплатили"), "paid"),
    (("оплатить", "заплатить", "платеж", "платёж", "к оплате"), "topay"),
    (("помощ", "help", "что умеешь", "меню"), "help"),
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
    keyboard: list[list[tuple[str, str]]] = field(default_factory=list)

    def reply_markup(self) -> dict | None:
        if not self.keyboard:
            return None
        return {
            "inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in self.keyboard]
        }


def _money(o: PaymentOccurrence) -> str:
    return html.escape(format_amount(o.amount_snapshot, o.currency_snapshot))


def _totals(items: list[PaymentOccurrence]) -> str:
    sums: dict[Currency, object] = {}
    for o in items:
        sums[o.currency_snapshot] = sums.get(o.currency_snapshot, 0) + o.amount_snapshot
    return " · ".join(html.escape(format_amount(v, c)) for c, v in sums.items()) or "—"


def _payments(n: int) -> str:
    n100 = abs(n) % 100
    n10 = n100 % 10
    if 11 <= n100 <= 14 or n10 == 0 or n10 >= 5:
        word = "платежей"
    elif n10 == 1:
        word = "платёж"
    else:
        word = "платежа"
    return f"{n} {word}"


def format_occurrence_card(o: PaymentOccurrence, today: date) -> str:
    info = compute_overdue(o.due_date, o.is_paid, o.paid_date, today)
    title = html.escape(o.title_snapshot)
    amount = _money(o)
    cur = html.escape(o.currency_snapshot.value)
    due = f"{o.due_date:%d.%m.%Y}"
    if o.is_paid:
        icon = "✅"
        late = f", с опозданием {info.overdue_days} дн." if info.is_overdue else ""
        tail = f"оплачено {o.paid_date:%d.%m.%Y}{late}"
    elif info.is_overdue:
        icon = "🔴"
        tail = f"просрочено на {info.overdue_days} дн."
    else:
        icon = "⏰"
        d = (o.due_date - today).days
        tail = due_phrase(d)
    return f"{icon} <b>{title}</b>\n{amount}{chr(0xA0)}({cur}) · срок {due} · {tail}"


def format_occurrence_line(o: PaymentOccurrence, today: date, title_max: int = 36) -> str:
    """Одна строка для списков — меньше высоты сообщения."""
    info = compute_overdue(o.due_date, o.is_paid, o.paid_date, today)
    title = html.escape(o.title_snapshot if len(o.title_snapshot) <= title_max else o.title_snapshot[: title_max - 1] + "…")
    amount = _money(o)
    if o.is_paid:
        icon, tail = "✅", f"опл. {o.paid_date:%d.%m}"
    elif info.is_overdue:
        icon, tail = "🔴", f"проср. {info.overdue_days} дн."
    else:
        icon, tail = "⏰", due_phrase((o.due_date - today).days)
    return f"{icon} {title} · {amount} · {o.due_date:%d.%m} · {tail}"


def format_paid_confirmation(occ: PaymentOccurrence, login: str) -> str:
    amount = format_money_bot(occ.amount_snapshot, occ.currency_snapshot)
    return (
        f"✅ <b>Оплачено</b> — отметил(а) {html.escape(login)}\n\n"
        f"<b>{html.escape(occ.title_snapshot)}</b>\n"
        f"Сумма: <b>{amount}</b>\n"
        f"Срок: {occ.due_date:%d.%m.%Y}\n"
        f"Дата оплаты: {occ.paid_date:%d.%m.%Y}"
    )


def error_block(title: str, reason: str, action: str, menu: bool = True) -> BotAnswer:
    text = f"<b>{html.escape(title)}</b>\n{html.escape(reason)}\n\n{html.escape(action)}"
    kb = [[("В меню", NAV_MENU)]] if menu else []
    return BotAnswer(text, kb)


def menu_keyboard(is_admin: bool) -> list[list[tuple[str, str]]]:
    rows = [
        [("К оплате", nav_callback("topay", 0)), ("Просрочено", nav_callback("overdue", 0))],
        [("На неделю", nav_callback("week", 0)), ("Оплачено", nav_callback("paid", 0))],
        [("Сводка", nav_callback("summary")), ("Открыть панель", nav_callback("site"))],
    ]
    if is_admin:
        rows.append([("Добавить платёж", nav_callback("add_hint"))])
    return rows


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
        return format_occurrence_card(o, self.clock.today())

    def menu(self, is_admin: bool = False) -> BotAnswer:
        return BotAnswer(MENU_INTRO, menu_keyboard(is_admin))

    def add_hint(self) -> BotAnswer:
        kb = [[("Отмена", NAV_CANCEL_ADD)]]
        return BotAnswer(ADD_USAGE, kb)

    def site_hint(self) -> BotAnswer:
        return BotAnswer(
            "<b>Панель в браузере</b>\n"
            "Команда /site пришлёт ссылку в личке. В группе откройте бота в личных сообщениях.",
            [[("В меню", NAV_MENU)]],
        )

    def screen(self, screen: ScreenId, page: int = 0, is_admin: bool = False) -> BotAnswer:
        if screen == "menu":
            return self.menu(is_admin)
        if screen == "add_hint":
            return self.add_hint()
        if screen == "site":
            return self.site_hint()
        if screen == "topay":
            return self.topay(page)
        if screen == "overdue":
            return self.overdue(page)
        if screen == "week":
            return self.week(page)
        if screen == "paid":
            return self.paid(page)
        if screen == "summary":
            return self.summary()
        return self.menu(is_admin)

    def _unpaid_list(
        self,
        screen: ScreenId,
        f: OccurrenceFilter,
        heading: str,
        empty_body: str,
        totals_label: str,
        page: int,
    ) -> BotAnswer:
        today = self.clock.today()
        offset = page * LIST_PAGE
        items, total = self.repo.query(f, today, "due_date", offset, LIST_PAGE)
        total_pages = max(1, math.ceil(total / LIST_PAGE)) if total else 1
        page = min(page, total_pages - 1)
        if page != offset // LIST_PAGE:
            offset = page * LIST_PAGE
            items, total = self.repo.query(f, today, "due_date", offset, LIST_PAGE)
        if not items:
            return BotAnswer(f"{heading}\n\n{empty_body}", [[("🏠 В меню", NAV_MENU)]])
        start_number = page * LIST_PAGE + 1
        lines = [f"{heading} · {_payments(total)}"]
        if total_pages > 1:
            lines.append(f"Страница {page + 1} из {total_pages}")
        lines.append("")
        body, _ = render_grouped_payment_lines(items, today, start_number)
        lines.extend(body)
        lines.append("")
        all_items = self.repo.all_filtered(f, today)
        lines.extend(totals_currency_lines(all_items, total, totals_label))
        keyboard = list_screen_keyboard(screen, items, page, total_pages, start_number)
        return BotAnswer("\n".join(lines), keyboard)

    def topay(self, page: int = 0) -> BotAnswer:
        return self._unpaid_list(
            "topay",
            self._scope(OccurrenceFilter(status="unpaid")),
            "💳 <b>К оплате</b>",
            "<b>Всё оплачено 🎉</b>\nНеоплаченных периодов нет.",
            "Всего к оплате",
            page,
        )

    def overdue(self, page: int = 0) -> BotAnswer:
        return self._unpaid_list(
            "overdue",
            self._scope(OccurrenceFilter(status="unpaid", overdue=True)),
            "🔴 <b>Просрочено</b>",
            "<b>Просрочек нет 🎉</b>\nОплата в день срока считается вовремя.",
            "Всего просрочено",
            page,
        )

    def week(self, page: int = 0) -> BotAnswer:
        until = self.clock.today() + timedelta(days=7)
        return self._unpaid_list(
            "week",
            self._scope(OccurrenceFilter(status="unpaid", overdue=False, date_to=until)),
            "📅 <b>На неделю</b>",
            "<b>На этой неделе платежей нет</b>\nПросроченные — в «Просрочено».",
            "Всего на 7 дней",
            page,
        )

    def paid(self, page: int = 0) -> BotAnswer:
        today = self.clock.today()
        items = [
            o
            for o in self.repo.all_filtered(self._scope(OccurrenceFilter(status="paid")), today)
            if o.paid_date and o.paid_date >= today - timedelta(days=30)
        ]
        items.sort(key=lambda o: o.paid_date, reverse=True)
        total = len(items)
        total_pages = max(1, math.ceil(total / LIST_PAGE)) if total else 1
        page = min(page, total_pages - 1)
        slice_ = items[page * LIST_PAGE : (page + 1) * LIST_PAGE]
        if not slice_:
            return BotAnswer(
                "✅ <b>Оплачено за 30 дней</b>\n\n<b>Оплат не было</b>\nСмотрю фактическую дату.",
                [[("🏠 В меню", NAV_MENU)]],
            )
        start_number = page * LIST_PAGE + 1
        lines = [f"✅ <b>Оплачено за 30 дней</b> · {_payments(total)}"]
        if total_pages > 1:
            lines.append(f"Страница {page + 1} из {total_pages}")
        lines.append("")
        body, _ = render_grouped_paid_lines(slice_, start_number)
        lines.extend(body)
        lines.append("")
        lines.extend(totals_currency_lines(items, total, "Всего за 30 дней"))
        keyboard = list_screen_keyboard("paid", slice_, page, total_pages, start_number, pay_buttons=False)
        return BotAnswer("\n".join(lines), keyboard)

    def summary(self) -> BotAnswer:
        s = SummaryService(self.db, self.clock).summary(self._scope(OccurrenceFilter()))
        lines = [f"📊 <b>Сводка</b> · {s.as_of:%d.%m.%Y}"]
        blocks: list[str] = []
        for c in s.currencies:
            if not c.total.count:
                continue
            sym = c.currency.value
            blocks.append(
                f"<b>{sym}</b>\n"
                f"к оплате {format_money_bot(c.unpaid.amount, c.currency)} ({c.unpaid.count})\n"
                f"просрочено {format_money_bot(c.overdue.amount, c.currency)} ({c.overdue.count})\n"
                f"оплачено {format_money_bot(c.paid.amount, c.currency)} ({c.paid.count})"
            )
        if not blocks:
            lines.append("\nПлатежей пока нет. Суммы по каждой валюте отдельно.")
        else:
            lines.append("")
            lines.extend(blocks)
        return BotAnswer("\n".join(lines), [[("🏠 В меню", NAV_MENU)]])

    def weekly_digest(self) -> BotAnswer:
        today = self.clock.today()
        overdue_f = self._scope(OccurrenceFilter(status="unpaid", overdue=True))
        week_until = today + timedelta(days=7)
        week_f = self._scope(OccurrenceFilter(status="unpaid", overdue=False, date_to=week_until))
        overdue_items, od_total = self.repo.query(overdue_f, today, "due_date", 0, LIST_PAGE)
        week_items, wk_total = self.repo.query(week_f, today, "due_date", 0, LIST_PAGE)
        lines = ["📬 <b>Сводка на неделю</b>", ""]
        btn_pairs: list[tuple[str, str]] = []
        line_num = 1
        if overdue_items:
            lines.append(f"🔴 <b>Просрочено</b> · {_payments(od_total)}")
            lines.append("")
            body, line_num = render_grouped_payment_lines(overdue_items, today, line_num)
            lines.extend(body)
            for i, o in enumerate(overdue_items):
                btn_pairs.append((f"✅ {i + 1}", list_paid_callback("overdue", o.id)))
        else:
            lines.append("🔴 <b>Просроченного нет</b>")
        lines.append("")
        if week_items:
            week_start = line_num
            lines.append(f"📅 <b>На неделю</b> · {_payments(wk_total)}")
            lines.append("")
            body, line_num = render_grouped_payment_lines(week_items, today, week_start)
            lines.extend(body)
            for i, o in enumerate(week_items):
                btn_pairs.append((f"✅ {week_start + i}", list_paid_callback("week", o.id)))
        else:
            lines.append("📅 <b>На неделе платежей нет</b>")
        lines.append("")
        unpaid_all = self.repo.all_filtered(self._scope(OccurrenceFilter(status="unpaid")), today)
        lines.extend(totals_topay_lines(unpaid_all, len(unpaid_all)))
        rows: list[list[tuple[str, str]]] = []
        row: list[tuple[str, str]] = []
        for label, cb in btn_pairs[:BUTTONS]:
            row.append((label, cb))
            if len(row) >= PAY_BTN_COLS:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([("💳 К оплате", nav_callback("topay", 0)), ("🏠 В меню", NAV_MENU)])
        return BotAnswer("\n".join(lines), rows)

    def payment_created_preview(self, payment) -> BotAnswer:
        rec = {"monthly": "ежемесячно", "weekly": "еженедельно", "quarterly": "ежеквартально", "yearly": "ежегодно"}
        text = (
            "<b>Платёж добавлен</b>\n\n"
            f"<b>{html.escape(payment.title)}</b>\n"
            f"{html.escape(format_amount(payment.amount, payment.currency))}{chr(0xA0)}"
            f"({payment.currency.value}) · {rec[payment.recurrence.value]}\n"
            f"Ближайший срок: {payment.first_due_date:%d.%m.%Y}"
        )
        kb = [
            [("Удалить этот платёж", f"undo:{payment.id}")],
            [("К оплате", nav_callback("topay", 0)), ("В меню", NAV_MENU)],
        ]
        return BotAnswer(text, kb)


def access_denied_answer(private: bool) -> BotAnswer:
    if private:
        reason = "Telegram не привязан к команде."
        action = "Откройте /start или привяжите аккаунт на сайте."
    else:
        reason = "Этот чат не привязан к команде."
        action = "Администратор: панель → Telegram → код /bind в группе."
    return error_block("Нет доступа", reason, action)
