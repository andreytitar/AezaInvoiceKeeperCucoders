"""Обработка нажатий inline-кнопки «Оплачено» (long polling в worker).

Правила те же, что у PATCH /payment-occurrences/{id}: вызывается OccurrenceService.mark.
Нажать может только пользователь, чей Telegram id привязан в профиле (users.telegram_user_id).
"""

from __future__ import annotations

import asyncio
import html
import logging
import uuid

from sqlalchemy.dialects.postgresql import insert

from app.domain.errors import DomainError
from app.domain.money import format_amount
from app.domain.status import PaymentStatus
from app.infrastructure.channels.telegram import TelegramClient, TelegramError
from app.infrastructure.request_context import RequestContext, request_context
from app.models import TelegramUpdatesOffset
from app.repositories.users import UserRepository
from app.domain.phrase import parse_payment_phrase
from app.services.payments import PaymentService
from app.services.receipt_scan import ReceiptScanService
from app.services.reminders import dispatch_now
from app.services.bot_answers import HELP, BotAnswers, command_for_text
from app.services.occurrences import OccurrenceService
from app.services.telegram_link import TelegramLinkService, get_bound_chat

log = logging.getLogger("app.telegram.updates")

CALLBACK_PAID = "paid:"  # под напоминанием: сообщение редактируется
CALLBACK_LIST_PAID = "lp:"
CALLBACK_UNDO = "undo:"  # удалить платёж, только что добавленный через /add  # под ответом на /topay и т. п.: отдельное сообщение


def paid_callback(occurrence_id: uuid.UUID) -> str:
    return f"{CALLBACK_PAID}{occurrence_id}"


class TelegramUpdateHandler:
    def __init__(self, container, client: TelegramClient) -> None:
        self.c = container
        self.client = client

    # --- смещение ---
    def load_offset(self) -> int | None:
        with self.c.session_factory() as db:
            row = db.get(TelegramUpdatesOffset, 1)
            return row.last_update_id + 1 if row else None

    def save_offset(self, update_id: int) -> None:
        with self.c.session_factory() as db:
            stmt = insert(TelegramUpdatesOffset).values(id=1, last_update_id=update_id)
            db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={"last_update_id": update_id}))
            db.commit()

    # --- обработка ---
    async def handle_update(self, update: dict) -> None:
        if update.get("message"):
            await self.handle_message(update["message"])
            return
        cq = update.get("callback_query")
        if not cq:
            return
        data = cq.get("data") or ""
        if data.startswith(CALLBACK_UNDO):
            try:
                await self._undo_add(cq, uuid.UUID(data[len(CALLBACK_UNDO):]))
            except ValueError:
                await self._answer(cq, "Некорректная кнопка", alert=True)
            return
        from_list = data.startswith(CALLBACK_LIST_PAID)
        prefix = CALLBACK_LIST_PAID if from_list else CALLBACK_PAID
        if not data.startswith(prefix):
            await self._answer(cq, "Неизвестная команда", alert=True)
            return
        try:
            occurrence_id = uuid.UUID(data[len(prefix):])
        except ValueError:
            await self._answer(cq, "Некорректная кнопка", alert=True)
            return
        tg_user = cq.get("from") or {}
        tg_id = tg_user.get("id")

        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
            if user is None:
                log.info("Нажатие от непривязанного Telegram-аккаунта", extra={"telegram_user_id": tg_id})
                await self._answer(
                    cq,
                    f"Ваш Telegram (id {tg_id}) не привязан к пользователю Invoice Keeper. "
                    "Откройте панель → «Привязать Telegram» или попросите администратора.",
                    alert=True,
                )
                return
            token = request_context.set(
                RequestContext(user_agent="telegram-bot", actor_id=user.id, actor_login=user.login)
            )
            try:
                svc = OccurrenceService(db, self.c.clock, self.c.settings)
                already_paid = svc.get(occurrence_id).is_paid
                occ = svc.mark(
                    occurrence_id,
                    status=PaymentStatus.PAID,
                    paid_date=None,
                    paid_date_provided=False,
                    actor=user,
                )
            except DomainError as exc:
                await self._answer(cq, exc.message, alert=True)
                return
            finally:
                request_context.reset(token)
            text = (
                f"<b>Оплачено</b>\n\n"
                f"<b>{html.escape(occ.title_snapshot)}</b>\n"
                f"Сумма: <b>{html.escape(format_amount(occ.amount_snapshot, occ.currency_snapshot))}</b> "
                f"({occ.currency_snapshot.value})\n"
                f"Срок: {occ.due_date:%d.%m.%Y}\n"
                f"Оплачено {occ.paid_date:%d.%m.%Y}, отметил(а) {html.escape(user.login)}"
            )
        await self._answer(cq, "Уже было отмечено как оплачено" if already_paid else "Отмечено как оплачено")
        msg = cq.get("message") or {}
        if from_list:
            # кнопка под списком: список не трогаем, отвечаем отдельным сообщением
            if not already_paid and (msg.get("chat") or {}).get("id") is not None:
                await self._send(msg["chat"]["id"], text, reply_to=msg.get("message_id"))
            return
        if msg.get("message_id") and (msg.get("chat") or {}).get("id") is not None:
            try:
                await self.client.edit_message_text(msg["chat"]["id"], msg["message_id"], text)
            except TelegramError as exc:
                # «message is not modified» при повторном нажатии — нормально
                log.info("Сообщение не отредактировано: %s", exc)

    # --- сообщения и команды ---
    async def _send(self, chat_id, text: str, reply_markup: dict | None = None, reply_to: int | None = None) -> None:
        try:
            await self.client.send_message(chat_id, text, reply_markup, reply_to=reply_to)
        except TelegramError as exc:
            log.warning("sendMessage: %s", exc)

    def _access(self, db, chat_id: int, tg_id: int | None):
        """Кто спрашивает: привязанный пользователь (в любом чате) или участник чата напоминаний."""
        user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
        bound = get_bound_chat(db, self.c.settings).chat_id
        in_bound_chat = bound is not None and str(chat_id) == str(bound)
        return user, (user is not None or in_bound_chat)

    async def handle_message(self, msg: dict) -> None:
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        tg_id = (msg.get("from") or {}).get("id")
        if chat_id is None:
            return
        private = chat.get("type") == "private"
        text = (msg.get("text") or msg.get("caption") or "").strip()

        if msg.get("photo") or msg.get("document"):
            if private:
                await self._scan_receipt(msg, chat_id, tg_id)
            return

        if text.startswith("/"):
            head, _, args = text.partition(" ")
            cmd = head[1:].split("@", 1)[0].lower()
            args = args.strip()
        elif private and text:
            cmd, args = command_for_text(text), ""
            if cmd is None:
                await self._send(chat_id, "Не понял вопрос. " + HELP)
                return
        else:
            return

        if cmd == "start":
            await self._cmd_start(chat_id, tg_id, args, private)
        elif cmd == "bind":
            await self._cmd_bind(chat_id, chat.get("title"), args, msg.get("message_id"))
        elif cmd == "help":
            await self._send(chat_id, HELP)
        elif cmd in ("topay", "overdue", "week", "paid", "summary", "add"):
            with self.c.session_factory() as db:
                user, allowed = self._access(db, chat_id, tg_id)
                if not allowed:
                    await self._send(
                        chat_id,
                        "Нет доступа. Привяжите Telegram в панели Invoice Keeper (кнопка «Привязать Telegram») "
                        "или спросите в чате, куда приходят напоминания.",
                    )
                    return
                if cmd == "add":
                    await self._cmd_add(db, user, chat_id, args, msg.get("message_id"))
                    return
                answer = getattr(BotAnswers(db, self.c.clock), cmd)()
            await self._send(chat_id, answer.text, answer.reply_markup())

    async def _cmd_add(self, db, user, chat_id, text: str, reply_to) -> None:
        if user is None or user.role != "admin":
            await self._send(chat_id, "Добавлять платежи может только администратор с привязанным Telegram.", reply_to=reply_to)
            return
        if not text:
            await self._send(chat_id, "Пример: <code>/add аренда 55000 руб каждое 5-е</code>", reply_to=reply_to)
            return
        token = request_context.set(RequestContext(user_agent="telegram-bot", actor_id=user.id, actor_login=user.login))
        try:
            parsed = parse_payment_phrase(text, self.c.clock.today())
            payment = PaymentService(db, self.c.clock, self.c.settings, self.c.channels).create(
                title=parsed.title,
                amount=parsed.amount,
                currency=parsed.currency,
                first_due_date=parsed.first_due_date,
                recurrence=parsed.recurrence,
                actor=user,
            )
        except DomainError as exc:
            await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}", reply_to=reply_to)
            return
        finally:
            request_context.reset(token)
        rec = {"monthly": "ежемесячно", "weekly": "еженедельно", "quarterly": "ежеквартально", "yearly": "ежегодно"}
        await self._send(
            chat_id,
            "Добавлен платёж:\n"
            f"<b>{html.escape(payment.title)}</b> — {html.escape(format_amount(payment.amount, payment.currency))} "
            f"({payment.currency.value}), {rec[payment.recurrence.value]}, ближайшая оплата "
            f"{payment.first_due_date:%d.%m.%Y}.",
            reply_markup={"inline_keyboard": [[{"text": "Удалить этот платёж", "callback_data": f"{CALLBACK_UNDO}{payment.id}"}]]},
            reply_to=reply_to,
        )
        await dispatch_now(self.c)  # срок близко — напоминание сразу

    async def _undo_add(self, cq: dict, payment_id: uuid.UUID) -> None:
        tg_id = (cq.get("from") or {}).get("id")
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
            if user is None or user.role != "admin":
                await self._answer(cq, "Удалять платежи может только администратор", alert=True)
                return
            try:
                p = PaymentService(db, self.c.clock, self.c.settings).delete(payment_id, actor=user)
            except DomainError as exc:
                await self._answer(cq, exc.message, alert=True)
                return
            title = p.title
        await self._answer(cq, "Платёж удалён")
        msg = cq.get("message") or {}
        if msg.get("message_id") and (msg.get("chat") or {}).get("id") is not None:
            try:
                await self.client.edit_message_text(
                    msg["chat"]["id"], msg["message_id"], f"Платёж <s>{html.escape(title)}</s> удалён."
                )
            except TelegramError:
                pass

    async def _scan_receipt(self, msg: dict, chat_id, tg_id) -> None:
        """Фото или PDF чека в личке: QR → поиск платежа → отметка оплаты и прикрепление чека."""
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
        if user is None:
            await self._send(chat_id, "Сначала привяжите Telegram в панели (кнопка «Telegram» → «Привязать Telegram»).")
            return
        if msg.get("photo"):
            file_id, name = msg["photo"][-1]["file_id"], None  # самое большое разрешение
        else:
            doc = msg["document"]
            file_id, name = doc["file_id"], doc.get("file_name")
            if (doc.get("file_size") or 0) > self.c.settings.receipt_max_bytes:
                await self._send(chat_id, "Файл больше 5 МБ.", reply_to=msg.get("message_id"))
                return
        try:
            info = await self.client.get_file(file_id)
            data = await self.client.download_file(info["file_path"], self.c.settings.receipt_max_bytes)
        except (TelegramError, KeyError) as exc:
            await self._send(chat_id, f"Не удалось скачать файл: {html.escape(str(exc))}", reply_to=msg.get("message_id"))
            return
        token = request_context.set(RequestContext(user_agent="telegram-bot", actor_id=user.id, actor_login=user.login))
        try:
            with self.c.session_factory() as db:
                actor = UserRepository(db).get(user.id)
                result = ReceiptScanService(db, self.c.clock, self.c.settings).scan(data, name, actor)
        except DomainError as exc:
            await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}", reply_to=msg.get("message_id"))
            return
        finally:
            request_context.reset(token)
        await self._send(chat_id, html.escape(result.message), reply_to=msg.get("message_id"))

    async def _cmd_start(self, chat_id, tg_id, code: str, private: bool) -> None:
        if not code:
            await self._send(chat_id, HELP)
            return
        if not private or not tg_id:
            await self._send(chat_id, "Привязка аккаунта работает только в личке с ботом.")
            return
        with self.c.session_factory() as db:
            try:
                user = TelegramLinkService(db, self.c.clock, self.c.settings).link_user(code, int(tg_id))
            except DomainError as exc:
                await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}")
                return
            login = user.login
        await self._send(
            chat_id,
            f"Готово: этот Telegram привязан к пользователю <b>{html.escape(login)}</b>.\n"
            "Теперь вы можете нажимать «Оплачено» под напоминаниями и спрашивать бота: /topay, /overdue, /summary.",
        )

    async def _cmd_bind(self, chat_id, title: str | None, code: str, reply_to) -> None:
        if not code:
            await self._send(chat_id, "Получите код в панели: «Платежи» → «Подключить чат», затем отправьте /bind КОД.")
            return
        with self.c.session_factory() as db:
            try:
                TelegramLinkService(db, self.c.clock, self.c.settings).bind_chat(code, int(chat_id), title)
            except DomainError as exc:
                await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}", reply_to=reply_to)
                return
        await self._send(
            chat_id,
            "Готово: напоминания о платежах будут приходить в этот чат.\n"
            "Спросите: /topay — что оплатить, /overdue — что просрочено, /summary — итоги.",
            reply_to=reply_to,
        )

    async def _answer(self, cq: dict, text: str, alert: bool = False) -> None:
        try:
            await self.client.answer_callback_query(cq["id"], text[:200], show_alert=alert)
        except TelegramError as exc:
            log.warning("answerCallbackQuery: %s", exc)

    async def poll_forever(self, stop: asyncio.Event) -> None:
        offset = self.load_offset()
        log.info("Telegram long polling запущен")
        while not stop.is_set():
            try:
                updates = await self.client.get_updates(offset, timeout=25)
            except TelegramError as exc:
                log.warning("getUpdates: %s", exc)
                await _sleep_or_stop(stop, 5)
                continue
            for upd in updates:
                try:
                    await self.handle_update(upd)
                except Exception:  # noqa: BLE001
                    log.exception("Ошибка обработки апдейта %s", upd.get("update_id"))
                offset = upd["update_id"] + 1
                self.save_offset(upd["update_id"])


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass
