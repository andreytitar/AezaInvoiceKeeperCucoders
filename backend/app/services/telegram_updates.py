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
from app.services.occurrences import OccurrenceService

log = logging.getLogger("app.telegram.updates")

CALLBACK_PAID = "paid:"


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
        cq = update.get("callback_query")
        if not cq:
            return
        data = cq.get("data") or ""
        if not data.startswith(CALLBACK_PAID):
            await self._answer(cq, "Неизвестная команда", alert=True)
            return
        try:
            occurrence_id = uuid.UUID(data[len(CALLBACK_PAID):])
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
                    "Попросите администратора указать этот id в вашем профиле.",
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
        if msg.get("message_id") and (msg.get("chat") or {}).get("id") is not None:
            try:
                await self.client.edit_message_text(msg["chat"]["id"], msg["message_id"], text)
            except TelegramError as exc:
                # «message is not modified» при повторном нажатии — нормально
                log.info("Сообщение не отредактировано: %s", exc)

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
