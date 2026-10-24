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

from app.domain.errors import DomainError, ValidationError
from app.domain.money import NBSP, format_amount
from app.domain.status import PaymentStatus
from app.infrastructure.channels.telegram import TelegramClient, TelegramError
from app.infrastructure.request_context import RequestContext, request_context
from app.models import Role, TeamKind, TelegramPending, TelegramUpdatesOffset
from app.repositories.teams import TeamRepository
from app.repositories.users import UserRepository
from app.domain.phrase import parse_payment_phrase
from app.services.payments import PaymentService
from app.services.receipt_scan import ReceiptScanService
from app.services.reminders import dispatch_now
from app.services.bot_answers import (
    HELP,
    NAV_MENU,
    NAV_NOOP,
    BotAnswer,
    BotAnswers,
    ScreenId,
    _CODE_TO_SCREEN,
    access_denied_answer,
    command_for_text,
    error_block,
    format_paid_confirmation,
    paid_undo_keyboard,
    parse_list_paid_callback,
    parse_nav_callback,
    parse_unpay_callback,
    screen_from_message_text,
)
from app.services.occurrences import OccurrenceService
from app.services.teams import TeamService
from app.services.bot_list_format import parse_page_from_message
from app.services.telegram_link import TelegramLinkService, magic_url

log = logging.getLogger("app.telegram.updates")

CALLBACK_PAID = "paid:"  # под напоминанием: сообщение редактируется
CALLBACK_LIST_PAID = "lp:"
CALLBACK_UNDO = "undo:"  # удалить платёж, только что добавленный через /add
CALLBACK_UNPAY = "unpay:"

UNLINKED_MENU = {
    "inline_keyboard": [
        [{"text": "Создать временную команду", "callback_data": "sb:new"}],
        [{"text": "Войти по коду приглашения", "callback_data": "sb:join"}],
        [{"text": "Войти на сайте", "callback_data": "sb:site"}],
    ]
}
UNLINKED_TEXT = (
    "Invoice Keeper напоминает о регулярных платежах. "
    "За три дня до срока пишет вам, что оплатить, что уже оплачено и что просрочено.\n\n"
    "Этот Telegram ещё не привязан к команде.\n"
    "Можно открыть временную команду на 24 часа, войти по коду приглашения "
    "или привязать уже существующий аккаунт с сайта."
)
SITE_TEXT = (
    "Учётная запись должна уже существовать. Войдите на сайте, откройте «Telegram» → «Привязать Telegram» "
    "и отправьте боту полученный код. Новый администратор основной команды так не создаётся."
)


def paid_callback(occurrence_id: uuid.UUID) -> str:
    return f"{CALLBACK_PAID}{occurrence_id}"


class TelegramUpdateHandler:
    def __init__(self, container, client: TelegramClient) -> None:
        self.c = container
        self.client = client
        self._busy: set[tuple[int, int]] = set()

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
        if data.startswith("sb:"):
            await self._sandbox_callback(cq, data)
            return
        if data == NAV_NOOP:
            await self._answer(cq, "")
            return
        if data.startswith(CALLBACK_UNPAY):
            await self._unpay_callback(cq, data)
            return
        nav = parse_nav_callback(data)
        if nav is not None:
            await self._nav_callback(cq, nav[0], nav[1])
            return
        if data.startswith(CALLBACK_UNDO):
            try:
                await self._undo_add(cq, uuid.UUID(data[len(CALLBACK_UNDO):]))
            except ValueError:
                await self._answer(cq, "Кнопка не сработала: данные устарели. Откройте список заново или напишите /help.", alert=True)
            return
        from_list = data.startswith(CALLBACK_LIST_PAID)
        list_screen: ScreenId | None = None
        if from_list:
            list_screen, occ_part = parse_list_paid_callback(data)
            prefix = CALLBACK_LIST_PAID
            id_body = occ_part
        elif data.startswith(CALLBACK_PAID):
            prefix = CALLBACK_PAID
            id_body = data[len(CALLBACK_PAID) :]
        else:
            await self._answer(cq, "Не узнаю эту команду. Нажмите «В меню» или /help.", alert=True)
            return
        try:
            occurrence_id = uuid.UUID(id_body)
        except ValueError:
            await self._answer(
                cq,
                "Кнопка устарела. Откройте список заново (/topay) или «В меню».",
                alert=True,
            )
            return
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        if chat_id is not None and message_id is not None:
            key = (int(chat_id), int(message_id))
            if key in self._busy:
                await self._answer(cq, "Уже обрабатываю…", alert=False)
                return
            self._busy.add(key)
        try:
            await self._handle_paid_callback(
                cq, occurrence_id, from_list, list_screen, msg.get("text") or ""
            )
        finally:
            if chat_id is not None and message_id is not None:
                self._busy.discard((int(chat_id), int(message_id)))

    async def _handle_paid_callback(
        self,
        cq: dict,
        occurrence_id: uuid.UUID,
        from_list: bool,
        list_screen: ScreenId | None,
        message_text: str,
    ) -> None:
        tg_user = cq.get("from") or {}
        tg_id = tg_user.get("id")

        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
            if user is None:
                log.info("Нажатие от непривязанного Telegram-аккаунта", extra={"telegram_user_id": tg_id})
                await self._answer(
                    cq,
                    "Чтобы отметить оплату, нужно быть в команде. "
                    "Пришлите код приглашения или откройте /start.",
                    alert=True,
                )
                return
            token = request_context.set(
                RequestContext(user_agent="telegram-bot", actor_id=user.id, actor_login=user.login)
            )
            try:
                svc = OccurrenceService(db, self.c.clock, self.c.settings)
                already_paid = svc.get(occurrence_id, user.team_id).is_paid
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
            is_admin = user.role == Role.ADMIN
            team_id = user.team_id
            login = user.login
            occ_frozen = occ
        await self._answer(cq, "Уже было отмечено как оплачено" if already_paid else "Отмечено как оплачено")
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        if from_list and chat_id is not None and message_id is not None:
            screen = list_screen or screen_from_message_text(message_text)
            page = parse_page_from_message(message_text)
            if screen in ("topay", "overdue", "week"):
                text = format_paid_confirmation(occ_frozen, login)
                markup = BotAnswer("", paid_undo_keyboard(screen, page, occ_frozen.id)).reply_markup()
                await self._edit_message(chat_id, message_id, text, markup)
                return
            with self.c.session_factory() as db:
                answer = BotAnswers(db, self.c.clock, team_id).screen(screen, page, is_admin)
            await self._edit_message(chat_id, message_id, answer.text, answer.reply_markup())
            return
        if chat_id is not None and message_id is not None:
            text = format_paid_confirmation(occ_frozen, login)
            await self._edit_message(chat_id, message_id, text, reply_markup={"inline_keyboard": []})

    async def _edit_message(
        self, chat_id, message_id: int, text: str, reply_markup: dict | None = None
    ) -> None:
        try:
            await self.client.edit_message_text(chat_id, message_id, text, reply_markup)
        except TelegramError as exc:
            if "message is not modified" in str(exc).lower():
                return
            log.info("Сообщение не отредактировано: %s", exc)

    async def _unpay_callback(self, cq: dict, data: str) -> None:
        parsed = parse_unpay_callback(data)
        if parsed is None:
            await self._answer(cq, "Кнопка устарела. Откройте /topay.", alert=True)
            return
        screen_code, page, occ_id_s = parsed
        try:
            occurrence_id = uuid.UUID(occ_id_s)
        except ValueError:
            await self._answer(cq, "Кнопка устарела.", alert=True)
            return
        tg_id = (cq.get("from") or {}).get("id")
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
            if user is None:
                await self._answer(cq, "Нужна привязка аккаунта.", alert=True)
                return
            token = request_context.set(
                RequestContext(user_agent="telegram-bot", actor_id=user.id, actor_login=user.login)
            )
            try:
                svc = OccurrenceService(db, self.c.clock, self.c.settings)
                svc.mark(
                    occurrence_id,
                    status=PaymentStatus.UNPAID,
                    paid_date=None,
                    paid_date_provided=False,
                    actor=user,
                )
            except DomainError as exc:
                await self._answer(cq, exc.message, alert=True)
                return
            finally:
                request_context.reset(token)
            is_admin = user.role == Role.ADMIN
            team_id = user.team_id
        await self._answer(cq, "Оплата отменена")
        if chat_id is None or message_id is None:
            return
        screen: ScreenId = _CODE_TO_SCREEN.get(screen_code) or screen_from_message_text(
            msg.get("text") or ""
        )
        with self.c.session_factory() as db:
            answer = BotAnswers(db, self.c.clock, team_id).screen(screen, page, is_admin)
        await self._edit_message(chat_id, message_id, answer.text, answer.reply_markup())

    async def _nav_callback(self, cq: dict, screen: ScreenId, page: int) -> None:
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        tg_id = (cq.get("from") or {}).get("id")
        private = (msg.get("chat") or {}).get("type") == "private"
        if chat_id is None or message_id is None:
            await self._answer(cq, "Сообщение недоступно. Напишите /help.", alert=True)
            return
        key = (int(chat_id), int(message_id))
        if key in self._busy:
            await self._answer(cq, "Уже обрабатываю…")
            return
        self._busy.add(key)
        await self._answer(cq, "")
        try:
            if screen == "site":
                await self._cmd_site(chat_id, tg_id, private)
                return
            with self.c.session_factory() as db:
                user, allowed, team_id = self._access(db, chat_id, tg_id, private)
                if not allowed:
                    ans = access_denied_answer(private)
                    await self._edit_message(chat_id, message_id, ans.text, ans.reply_markup())
                    return
                is_admin = user is not None and user.role == Role.ADMIN
                answer = BotAnswers(db, self.c.clock, team_id).screen(screen, page, is_admin)
            await self._edit_message(chat_id, message_id, answer.text, answer.reply_markup())
        finally:
            self._busy.discard(key)

    # --- сообщения и команды ---
    async def _send(self, chat_id, text: str, reply_markup: dict | None = None, reply_to: int | None = None) -> None:
        try:
            await self.client.send_message(chat_id, text, reply_markup, reply_to=reply_to)
        except TelegramError as exc:
            log.warning("sendMessage: %s", exc)

    def _access(self, db, chat_id: int, tg_id: int | None, private: bool):
        """Личка — только привязанный пользователь своей команды. Группа — чат, привязанный к команде.

        Кнопка «Оплачено» сюда не смотрит: её проверяет принадлежность telegram id к команде периода.
        """
        user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
        if private:
            return user, user is not None, (user.team_id if user else None)
        team = TeamRepository(db).get_by_chat_id(int(chat_id))
        if team is None:
            return user, False, None
        return user, True, team.id

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

        if private and text and not text.startswith("/") and tg_id and await self._pending_invite(chat_id, int(tg_id), text):
            return

        if text.startswith("/"):
            head, _, args = text.partition(" ")
            cmd = head[1:].split("@", 1)[0].lower()
            args = args.strip()
        elif private and text:
            cmd, args = command_for_text(text), ""
            if cmd is None:
                await self._send(
                    chat_id,
                    "Пока не разобрал сообщение. Напишите, например, «что просрочено» или откройте /help.",
                )
                return
        else:
            return

        if cmd == "start":
            await self._cmd_start(chat_id, tg_id, args, private)
        elif cmd == "join":
            await self._cmd_join(chat_id, tg_id, args, private)
        elif cmd == "bind":
            await self._cmd_bind(chat_id, chat.get("title"), args, msg.get("message_id"), tg_id, private)
        elif cmd == "help":
            with self.c.session_factory() as db:
                user, allowed, team_id = self._access(db, chat_id, tg_id, private)
                if allowed and user is not None:
                    answer = BotAnswers(db, self.c.clock, team_id).menu(user.role == Role.ADMIN)
                else:
                    answer = BotAnswer(HELP, [[("В меню", NAV_MENU)]]) if private else BotAnswer(HELP, [])
            await self._send(chat_id, answer.text, answer.reply_markup())
        elif cmd == "site":
            await self._cmd_site(chat_id, tg_id, private)
        elif cmd in ("topay", "overdue", "week", "paid", "summary", "add"):
            with self.c.session_factory() as db:
                user, allowed, team_id = self._access(db, chat_id, tg_id, private)
                if not allowed:
                    ans = access_denied_answer(private)
                    await self._send(chat_id, ans.text, ans.reply_markup())
                    return
                is_admin = user is not None and user.role == Role.ADMIN
                if cmd == "add":
                    await self._cmd_add(db, user, chat_id, args, msg.get("message_id"), team_id)
                    return
                screen: ScreenId = cmd  # type: ignore[assignment]
                answer = BotAnswers(db, self.c.clock, team_id).screen(screen, 0, is_admin)
            await self._send(chat_id, answer.text, answer.reply_markup())

    async def _cmd_add(self, db, user, chat_id, text: str, reply_to, team_id) -> None:
        if user is None or user.role != Role.ADMIN or user.team_id != team_id:
            ans = error_block(
                "Только администратор",
                "Добавлять платежи может администратор команды.",
                "Попросите администратора или откройте меню.",
            )
            await self._send(chat_id, ans.text, ans.reply_markup(), reply_to=reply_to)
            return
        if not text:
            hint = BotAnswers(db, self.c.clock, team_id).add_hint()
            await self._send(chat_id, hint.text, hint.reply_markup(), reply_to=reply_to)
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
        except ValidationError as exc:
            await self._send(chat_id, html.escape(exc.message), reply_to=reply_to)
            return
        except DomainError as exc:
            await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}", reply_to=reply_to)
            return
        finally:
            request_context.reset(token)
        preview = BotAnswers(db, self.c.clock, team_id).payment_created_preview(payment)
        await self._send(chat_id, preview.text, preview.reply_markup(), reply_to=reply_to)
        await dispatch_now(self.c)  # срок близко — напоминание сразу

    async def _undo_add(self, cq: dict, payment_id: uuid.UUID) -> None:
        tg_id = (cq.get("from") or {}).get("id")
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id)) if tg_id else None
            if user is None or user.role != Role.ADMIN:
                await self._answer(
                    cq,
                    "Удалить платёж может только администратор. Попросите его, если эта запись больше не нужна.",
                    alert=True,
                )
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
            ans = error_block(
                "Нужна привязка",
                "Telegram не привязан к аккаунту.",
                "На сайте: «Telegram» → «Привязать Telegram».",
            )
            await self._send(chat_id, ans.text, ans.reply_markup(), reply_to=msg.get("message_id"))
            return
        await self._send(
            chat_id,
            "📎 Получил файл, распознаю QR…",
            reply_to=msg.get("message_id"),
        )
        try:
            await self.client.send_chat_action(chat_id, "upload_document")
        except TelegramError:
            pass
        if msg.get("photo"):
            file_id, name = msg["photo"][-1]["file_id"], None  # самое большое разрешение
        else:
            doc = msg["document"]
            file_id, name = doc["file_id"], doc.get("file_name")
            if (doc.get("file_size") or 0) > self.c.settings.receipt_max_bytes:
                await self._send(
                    chat_id,
                    "Файл больше 5 МБ, поэтому не могу его принять.",
                    reply_to=msg.get("message_id"),
                )
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
        icons = {
            "matched": "✅",
            "already_counted": "ℹ️",
            "no_match": "⚠️",
            "not_receipt": "⚠️",
        }
        icon = icons.get(result.status, "ℹ️")
        body = html.escape(result.message)
        kb = {"inline_keyboard": [[{"text": "К оплате", "callback_data": "nav:t:0"}, {"text": "В меню", "callback_data": NAV_MENU}]]}
        await self._send(
            chat_id,
            f"{icon} {body}",
            reply_markup=kb,
            reply_to=msg.get("message_id"),
        )

    async def _cmd_start(self, chat_id, tg_id, code: str, private: bool) -> None:
        if not private or not tg_id:
            await self._send(chat_id, "Привязка аккаунта работает только в личке с ботом.")
            return
        if code.startswith("weblogin_"):
            await self._cmd_web_login(chat_id, int(tg_id), code)
            return
        if code:
            # Код с сайта привязывает уже существующего пользователя и не создаёт администратора.
            with self.c.session_factory() as db:
                try:
                    user = TelegramLinkService(db, self.c.clock, self.c.settings).link_user(code, int(tg_id))
                except DomainError as exc:
                    await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}")
                    return
                login = user.login
            kb = {"inline_keyboard": [[{"text": "В меню", "callback_data": NAV_MENU}]]}
            await self._send(
                chat_id,
                f"Готово: Telegram привязан к <b>{html.escape(login)}</b>.\n"
                "Можно нажимать «Оплачено» под напоминаниями и открыть меню ниже.",
                reply_markup=kb,
            )
            return
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id))
            if user is None:
                await self._send(chat_id, UNLINKED_TEXT, UNLINKED_MENU)
                return
            if user.team.kind == TeamKind.PRIMARY:
                answer = BotAnswers(db, self.c.clock, user.team_id).menu(user.role == Role.ADMIN)
                await self._send(chat_id, answer.text, answer.reply_markup())
                return
            await self._send_sandbox_home(db, chat_id, user)

    async def _cmd_web_login(self, chat_id, tg_id: int, payload: str) -> None:
        """Start из кнопки сайта: код запоминает telegram id, решение принимает страница входа."""
        with self.c.session_factory() as db:
            try:
                TelegramLinkService(db, self.c.clock, self.c.settings).claim_web_login(payload, tg_id)
            except DomainError as exc:
                await self._send(chat_id, html.escape(exc.message))
                return
        await self._send(chat_id, "Вход на сайт подтверждён. Вернитесь в браузер — страница войдёт сама.")

    async def _cmd_join(self, chat_id, tg_id, code: str, private: bool) -> None:
        if not private or not tg_id:
            await self._send(
                chat_id,
                "В группу по коду войти нельзя. Откройте личный чат со мной и отправьте /join и код приглашения.",
            )
            return
        if not code:
            await self._arm_invite(int(tg_id))
            await self._send(chat_id, "Кода пока нет. Пришлите код приглашения следующим сообщением.")
            return
        await self._join_invite(chat_id, int(tg_id), code)

    async def _cmd_bind(self, chat_id, title: str | None, code: str, reply_to, sender_tg, private: bool) -> None:
        if private:
            await self._send(
                chat_id,
                "Отсюда чат не привяжется: /bind нужен в группе, где есть бот и где ему можно писать. "
                "Откройте эту группу и отправьте команду там.",
            )
            return
        if not code:
            await self._send(
                chat_id,
                "Кода нет, чат пока не привязан. Возьмите его в панели: «Telegram» → «Подключить чат» — "
                "и отправьте в этой группе /bind и код.",
            )
            return
        with self.c.session_factory() as db:
            try:
                admin = TelegramLinkService(db, self.c.clock, self.c.settings).bind_chat(
                    code, int(chat_id), title, int(sender_tg) if sender_tg is not None else None
                )
            except DomainError as exc:
                await self._send(chat_id, f"Чат не привязан. {html.escape(exc.message)}", reply_to=reply_to)
                return
            admin_tg = admin.telegram_user_id
            bound_title = title or str(chat_id)
        menu_kb = {"inline_keyboard": [[{"text": "К оплате", "callback_data": "nav:t:0"}, {"text": "В меню", "callback_data": NAV_MENU}]]}
        await self._send(
            chat_id,
            "Группа привязана. Напоминания команды будут здесь.\n"
            "Откройте «К оплате» или /help — меню разделов.",
            reply_markup=menu_kb,
            reply_to=reply_to,
        )
        if admin_tg is not None:
            await self._send(
                admin_tg,
                f"Группа «{html.escape(bound_title)}» привязана. "
                "Напоминания этой команды будут приходить туда. В том чате можно спросить /topay.",
            )

    async def _sandbox_callback(self, cq: dict, data: str) -> None:
        msg = cq.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        tg_id = (cq.get("from") or {}).get("id")
        if chat.get("type") != "private" or chat_id is None or tg_id is None:
            await self._answer(
                cq, "Это работает в личном чате. Откройте диалог со мной и нажмите кнопку там.", alert=True
            )
            return
        await self._answer(cq, "Ок")
        if data == "sb:new":
            await self._create_sandbox(chat_id, int(tg_id))
        elif data == "sb:join":
            await self._arm_invite(int(tg_id))
            await self._send(
                chat_id,
                "Кода пока нет. Пришлите код приглашения следующим сообщением или командой /join и код.",
            )
        elif data == "sb:site":
            await self._send(chat_id, SITE_TEXT)
        elif data == "sb:bind":
            await self._issue_bind_code(chat_id, int(tg_id))
        else:
            await self._send(chat_id, "Не узнаю эту команду. Напишите /help — покажу, что умею.")

    async def _create_sandbox(self, chat_id, tg_id: int) -> None:
        with self.c.session_factory() as db:
            existing = UserRepository(db).get_by_telegram_id(tg_id)
            if existing is not None:
                if existing.team.kind == TeamKind.PRIMARY:
                    await self._send(chat_id, HELP)
                else:
                    await self._send_sandbox_home(db, chat_id, existing)
                return
            try:
                created = TeamService(db, self.c.clock, self.c.settings).create_sandbox(tg_id)
            except DomainError as exc:
                await self._send(chat_id, f"Не получилось: {html.escape(exc.message)}")
                return
            admin_link = magic_url(self.c.settings, created.admin_code)
            employee_link = magic_url(self.c.settings, created.employee_code)
            when = created.expires_at.astimezone(self.c.settings.tz)
        await self._send(
            chat_id,
            "Временная команда создана. Через 24 часа она удалится вместе с платежами и пользователями "
            f"({when:%d.%m.%Y %H:%M}).\n\n"
            f'<a href="{html.escape(admin_link)}">Открыть панель</a> — вход администратором, ссылка одноразовая.\n'
            f'<a href="{html.escape(employee_link)}">Зайти как сотрудник</a> — тот же кабинет глазами пользователя «сотрудник».\n'
            f"Пригласить коллегу: код <code>{html.escape(created.invite_code)}</code> "
            f"(коллега пишет боту <code>/join {html.escape(created.invite_code)}</code>).\n"
            "Привязать группу — кнопка ниже. Пока группа не привязана, напоминания приходят вам в личку.\n\n"
            "Уже есть демо-платежи: аренда в рублях, сервер в долларах, подписка в евро.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Открыть панель", "url": admin_link}],
                    [{"text": "Зайти как сотрудник", "url": employee_link}],
                    [{"text": "Привязать группу", "callback_data": "sb:bind"}],
                ]
            },
        )

    async def _send_sandbox_home(self, db, chat_id, user) -> None:
        svc = TeamService(db, self.c.clock, self.c.settings)
        try:
            admin_code = svc.magic_for(user if user.role == Role.ADMIN else user)
        except DomainError as exc:
            await self._send(chat_id, html.escape(exc.message))
            return
        own_link = magic_url(self.c.settings, admin_code)
        rows = [[{"text": "Открыть панель", "url": own_link}]]
        lines = [
            "Снова открыта ваша временная команда.",
            f'<a href="{html.escape(own_link)}">Открыть панель</a> — одноразовая ссылка.',
        ]
        if user.role == Role.ADMIN:
            employee = svc.employee_of(user.team_id)
            if employee is not None:
                try:
                    emp_link = magic_url(self.c.settings, svc.magic_for(employee))
                    lines.append(f'<a href="{html.escape(emp_link)}">Зайти как сотрудник</a>')
                    rows.append([{"text": "Зайти как сотрудник", "url": emp_link}])
                except DomainError:
                    pass
            if user.team.invite_code:
                lines.append(
                    f"Пригласить коллегу: <code>{html.escape(user.team.invite_code)}</code> "
                    f"(<code>/join {html.escape(user.team.invite_code)}</code>)."
                )
            title = user.team.telegram_chat_title
            if user.team.telegram_chat_id:
                lines.append(f"Группа привязана: {html.escape(title or str(user.team.telegram_chat_id))}.")
            else:
                lines.append("Группа не привязана — напоминания приходят вам в личку.")
            rows.append([{"text": "Привязать группу", "callback_data": "sb:bind"}])
        markup = {"inline_keyboard": rows}
        when = user.team.expires_at
        if when is not None:
            lines.append(f"Команда удалится {when.astimezone(self.c.settings.tz):%d.%m.%Y %H:%M}.")
        await self._send(chat_id, "\n".join(lines), reply_markup=markup)

    async def _arm_invite(self, tg_id: int) -> None:
        now = self.c.clock.now()
        from datetime import timedelta

        with self.c.session_factory() as db:
            stmt = insert(TelegramPending).values(
                telegram_user_id=tg_id, action="await_invite", expires_at=now + timedelta(minutes=15)
            )
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["telegram_user_id"],
                    set_={"action": "await_invite", "expires_at": now + timedelta(minutes=15)},
                )
            )
            db.commit()

    async def _pending_invite(self, chat_id, tg_id: int, text: str) -> bool:
        with self.c.session_factory() as db:
            row = db.get(TelegramPending, tg_id)
            if row is None or row.action != "await_invite" or row.expires_at < self.c.clock.now():
                return False
            db.delete(row)
            db.commit()
        await self._join_invite(chat_id, tg_id, text)
        return True

    async def _join_invite(self, chat_id, tg_id: int, code: str) -> None:
        with self.c.session_factory() as db:
            try:
                user = TeamService(db, self.c.clock, self.c.settings).join_by_invite(tg_id, code)
            except DomainError as exc:
                hint = "" if exc.code == "telegram_taken" else " Проверьте код у администратора или откройте /start."
                await self._send(chat_id, f"В команду пока не вошли. {html.escape(exc.message)}.{hint}")
                return
            login = user.login
            try:
                link = magic_url(self.c.settings, TeamService(db, self.c.clock, self.c.settings).magic_for(user))
            except DomainError:
                link = None
        text = (
            f"Вы в команде как <b>{html.escape(login)}</b>.\n"
            "Откройте меню или /topay — список платежей."
        )
        rows = [[{"text": "В меню", "callback_data": NAV_MENU}]]
        if link:
            text += f'\n<a href="{html.escape(link)}">Открыть панель</a> — одноразовая ссылка.'
            rows.insert(0, [{"text": "Открыть панель", "url": link}])
        await self._send(chat_id, text, reply_markup={"inline_keyboard": rows})

    async def _cmd_site(self, chat_id, tg_id, private: bool) -> None:
        if not private or not tg_id:
            await self._send(chat_id, "Ссылку на панель бот присылает только в личке.")
            return
        base = (self.c.settings.public_base_url or "http://localhost:8000").rstrip("/")
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(int(tg_id))
            if user is None:
                await self._send(chat_id, UNLINKED_TEXT, UNLINKED_MENU)
                return
            if user.team.kind != TeamKind.SANDBOX:
                await self._send(
                    chat_id,
                    f'Панель: <a href="{html.escape(base)}">открыть сайт</a>. Войдите своим логином и паролем.',
                    reply_markup={"inline_keyboard": [[{"text": "Открыть сайт", "url": base}]]},
                )
                return
            try:
                link = magic_url(self.c.settings, TeamService(db, self.c.clock, self.c.settings).magic_for(user))
            except DomainError as exc:
                await self._send(chat_id, html.escape(exc.message))
                return
        await self._send(
            chat_id,
            f'<a href="{html.escape(link)}">Открыть панель</a> — ссылка одноразовая, откроется ваша временная команда.',
            reply_markup={"inline_keyboard": [[{"text": "Открыть панель", "url": link}]]},
        )

    async def _issue_bind_code(self, chat_id, tg_id: int) -> None:
        with self.c.session_factory() as db:
            user = UserRepository(db).get_by_telegram_id(tg_id)
            if user is None or user.role != Role.ADMIN:
                await self._send(
                    chat_id,
                    "Код для группы выдаёт администратор. Попросите его нажать «Привязать группу».",
                )
                return
            code = TelegramLinkService(db, self.c.clock, self.c.settings).create_chat_code(user)
            token = code.code
        await self._send(
            chat_id,
            "Код готов и действует 15 минут. Добавьте бота в группу, разрешите ему писать и отправьте там:\n"
            f"<code>/bind {html.escape(token)}</code>\n"
            "Эта временная команда не привяжет основной чат из настроек — нужна своя группа.",
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
