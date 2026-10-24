import asyncio

from app.services.telegram_updates import TelegramUpdateHandler
from tests.worker.test_telegram_bot import msg
from tests.worker.test_telegram_button import FakeTelegramClient


def link_admin(admin):
    me = admin.get("/api/v1/auth/me").json()
    # системного админа нельзя менять через API — привязываем через одноразовую ссылку
    return admin.post("/api/v1/telegram/link").json()["command"], me


def run(container, update, client=None):
    client = client or FakeTelegramClient()
    asyncio.run(TelegramUpdateHandler(container, client).handle_update(update))
    return client


def test_admin_adds_payment_by_phrase_and_undoes(admin, container, fake_channel):
    cmd, _ = link_admin(admin)
    run(container, msg(cmd, chat_id=777, tg_id=777, chat_type="private"))
    c = run(container, msg("/add сервер aeza 25$ 26 числа", chat_id=777, tg_id=777, chat_type="private"))
    text = c.messages[0]["text"]
    assert "Сервер aeza" in text and "25,00\u00a0$\u00a0(USD)" in text and "26.10.2026" in text
    payments = admin.get("/api/v1/recurring-payments").json()
    assert [(p["title"], p["amount"], p["currency"]) for p in payments] == [("Сервер aeza", "25.00", "USD")]
    assert len(fake_channel.sent) == 1  # срок через 2 дня — напоминание сразу
    undo = c.messages[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    c2 = run(container, {"update_id": 9, "callback_query": {"id": "q", "from": {"id": 777}, "data": undo,
                                                            "message": {"message_id": 1, "chat": {"id": 777}}}})
    assert c2.answers[0][1] == "Платёж удалён" and "удалён" in c2.edits[0][2]
    assert admin.get("/api/v1/recurring-payments").json() == []


def test_user_cannot_add(user, regular_user, admin, container):
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": 555})
    c = run(container, msg("/add аренда 1000 руб 5 числа", chat_id=555, chat_type="private"))
    assert "только администратор" in c.messages[0]["text"]
    assert admin.get("/api/v1/recurring-payments").json() == []


def test_bad_phrase(admin, container):
    cmd, _ = link_admin(admin)
    run(container, msg(cmd, chat_id=777, tg_id=777, chat_type="private"))
    c = run(container, msg("/add просто текст", chat_id=777, tg_id=777, chat_type="private"))
    assert "Не получилось" in c.messages[0]["text"]


def test_parse_endpoint(admin):
    r = admin.post("/api/v1/recurring-payments/parse", json={"text": "аренда офиса 55 000 руб каждое 5-е"})
    assert r.status_code == 200
    assert r.json() == {"title": "Аренда офиса", "amount": "55000", "currency": "RUB", "first_due_date": "2026-11-05", "recurrence": "monthly"}
    assert admin.post("/api/v1/recurring-payments/parse", json={"text": "ерунда"}).status_code == 422
