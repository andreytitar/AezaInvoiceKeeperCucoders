"""Кнопка «Оплачено» под напоминанием: права, идемпотентность, редактирование сообщения."""

import asyncio
from datetime import date

from app.services.telegram_updates import TelegramUpdateHandler, paid_callback
from tests.integration.helpers import create_payment, occurrences_of


class FakeTelegramClient:
    def __init__(self, updates=None):
        self.answers, self.edits, self.messages = [], [], []
        self._updates = list(updates or [])

    async def send_message(self, chat_id, text, reply_markup=None, reply_to=None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "reply_to": reply_to})
        return {"message_id": len(self.messages), "chat": {"id": chat_id}}

    async def answer_callback_query(self, callback_query_id, text, show_alert=False):
        self.answers.append((callback_query_id, text, show_alert))

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append((chat_id, message_id, text, reply_markup))

    async def get_updates(self, offset, timeout=25):
        await asyncio.sleep(0.01)  # как настоящий long polling: отдаём управление циклу
        batch, self._updates = self._updates, []
        return [u for u in batch if offset is None or u["update_id"] >= offset]

    async def send_chat_action(self, chat_id, action="typing"):
        return None


def press(occurrence_id, tg_user_id, update_id=1, data=None):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cq{update_id}",
            "from": {"id": tg_user_id},
            "data": data or paid_callback(occurrence_id),
            "message": {"message_id": 77, "chat": {"id": -100500}},
        },
    }


def handle(container, client, update):
    asyncio.run(TelegramUpdateHandler(container, client).handle_update(update))


def setup(admin, regular_user, telegram_id=555):
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": telegram_id})
    p = create_payment(admin, first_due_date="2026-10-26")
    return occurrences_of(admin, p["id"])[0]


def test_reminder_has_paid_button(admin, fake_channel):
    p = create_payment(admin, first_due_date="2026-10-26")
    occ = occurrences_of(admin, p["id"])[0]
    msg = fake_channel.sent[0][0]
    assert [(a.text, a.callback_data) for a in msg.actions] == [("Оплачено", f"paid:{occ['id']}")]


def test_linked_user_marks_paid_and_message_is_edited(admin, user, regular_user, container):
    occ = setup(admin, regular_user)
    client = FakeTelegramClient()
    handle(container, client, press(occ["id"], 555))
    r = user.get(f"/api/v1/payment-occurrences/{occ['id']}").json()
    assert r["status"] == "paid" and r["paid_date"] == "2026-10-24"
    assert client.answers == [("cq1", "Отмечено как оплачено", False)]
    chat, mid, text, _markup = client.edits[0]
    assert (chat, mid) == (-100500, 77) and "✅" in text and "ivan" in text and "24.10.2026" in text
    assert "55\u00a0000\u00a0₽" in text and "55 000" not in text
    log = admin.get("/api/v1/audit-logs", params={"action": "occurrence.paid"}).json()["items"][0]
    assert log["actor_login"] == "ivan" and log["user_agent"] == "telegram-bot"


def test_repeat_press_is_idempotent(admin, user, regular_user, container, clock):
    occ = setup(admin, regular_user)
    client = FakeTelegramClient()
    handle(container, client, press(occ["id"], 555, 1))
    clock.advance(days=1)
    handle(container, client, press(occ["id"], 555, 2))
    r = user.get(f"/api/v1/payment-occurrences/{occ['id']}").json()
    assert r["paid_date"] == "2026-10-24"  # дата первой отметки сохранилась
    assert client.answers[1][1] == "Уже было отмечено как оплачено"
    assert len(admin.get("/api/v1/audit-logs", params={"action": "occurrence.paid"}).json()["items"]) == 1


def test_unlinked_account_rejected_with_alert(admin, user, regular_user, container):
    occ = setup(admin, regular_user)
    client = FakeTelegramClient()
    handle(container, client, press(occ["id"], 999))
    assert client.answers[0][2] is True
    assert "в команде" in client.answers[0][1] and "/start" in client.answers[0][1]
    assert client.edits == []
    assert user.get(f"/api/v1/payment-occurrences/{occ['id']}").json()["status"] == "unpaid"


def test_deleted_user_cannot_press(admin, user, regular_user, container):
    occ = setup(admin, regular_user)
    admin.delete(f"/api/v1/users/{regular_user.id}")
    client = FakeTelegramClient()
    handle(container, client, press(occ["id"], 555))
    assert client.answers[0][2] is True
    assert admin.get(f"/api/v1/payment-occurrences/{occ['id']}").json()["status"] == "unpaid"


def test_garbage_callback(admin, regular_user, container):
    setup(admin, regular_user)
    client = FakeTelegramClient()
    handle(container, client, press(None, 555, data="paid:not-a-uuid"))
    handle(container, client, press(None, 555, 2, data="drop:all"))
    handle(container, client, press(None, 555, 3, data="paid:00000000-0000-0000-0000-000000000000"))
    assert all(a[2] for a in client.answers) and len(client.answers) == 3


def test_offset_persisted_across_restart(admin, regular_user, container):
    occ = setup(admin, regular_user)
    client = FakeTelegramClient([press(occ["id"], 555, 41), press(occ["id"], 555, 42)])
    handler = TelegramUpdateHandler(container, client)
    stop = asyncio.Event()

    async def run_once():
        task = asyncio.create_task(handler.poll_forever(stop))
        await asyncio.sleep(0.2)
        stop.set()
        await task

    asyncio.run(run_once())
    assert len(client.answers) == 2
    assert TelegramUpdateHandler(container, FakeTelegramClient()).load_offset() == 43


def test_paid_via_button_cancels_pending_reminders(admin, regular_user, container, clock, fake_channel):
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": 555})
    p = create_payment(admin, first_due_date="2026-11-20")
    occ = occurrences_of(admin, p["id"])[0]
    handle(container, FakeTelegramClient(), press(occ["id"], 555))
    clock.set_today(date(2026, 11, 19))
    from tests.worker.test_reminders import tick

    tick(container)
    assert fake_channel.sent == []
