"""Бот: привязка без ввода id (/start, /bind), ответы на вопросы, кнопки под списками."""

import asyncio
from datetime import timedelta

from app.repositories.users import UserRepository
from app.services.telegram_link import chat_provider
from tests.integration.helpers import create_payment, occurrences_of
from tests.worker.test_telegram_button import FakeTelegramClient

from app.services.telegram_updates import TelegramUpdateHandler

GROUP = -100777
ADMIN_TG = 777


def link_system_admin(container, tg_id=ADMIN_TG):
    with container.session_factory() as db:
        admin = UserRepository(db).get_by_login("admin")
        admin.telegram_user_id = tg_id
        db.commit()


def msg(text, chat_id=GROUP, tg_id=555, chat_type="supergroup", title="Бухгалтерия", update_id=1):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "chat": {"id": chat_id, "type": chat_type, "title": title},
            "from": {"id": tg_id},
            "text": text,
        },
    }


def send(container, update, client=None):
    client = client or FakeTelegramClient()
    asyncio.run(TelegramUpdateHandler(container, client).handle_update(update))
    return client


def test_link_user_via_start_deep_link(user, container):
    link = user.post("/api/v1/telegram/link").json()
    assert link["command"].startswith("/start ") and link["url"] is None  # без токена бота ссылки нет
    c = send(container, msg(link["command"], chat_id=555, chat_type="private"))
    assert "привязан к пользователю <b>ivan</b>" in c.messages[0]["text"]
    assert user.get("/api/v1/auth/me").json()["telegram_user_id"] == 555
    assert user.get("/api/v1/telegram/status").json()["me_linked"] is True
    # код одноразовый
    c = send(container, msg(link["command"], chat_id=556, tg_id=556, chat_type="private"))
    assert "уже использован" in c.messages[0]["text"]
    assert user.delete("/api/v1/telegram/link").status_code == 204
    assert user.get("/api/v1/auth/me").json()["telegram_user_id"] is None


def test_link_code_expires(user, container, clock):
    link = user.post("/api/v1/telegram/link").json()
    clock.advance(minutes=16)
    c = send(container, msg(link["command"], chat_id=555, chat_type="private"))
    assert "истёк" in c.messages[0]["text"]


def test_start_in_group_rejected(user, container):
    link = user.post("/api/v1/telegram/link").json()
    c = send(container, msg(link["command"]))
    assert "только в личке" in c.messages[0]["text"]


def test_bind_chat_and_reminders_go_there(admin, user, container):
    assert user.post("/api/v1/telegram/chat-link").status_code == 403
    link_system_admin(container, 555)
    code = admin.post("/api/v1/telegram/chat-link").json()
    assert code["command"].startswith("/bind ")
    c = send(container, msg(code["command"] + "", title="Бухгалтерия", tg_id=555))
    assert "будут приходить в этот чат" in c.messages[0]["text"]
    st = admin.get("/api/v1/telegram/status").json()
    assert st["chat_bound"] and st["chat_title"] == "Бухгалтерия" and st["chat_source"] == "bind"
    assert chat_provider(container.session_factory, container.settings)() == str(GROUP)
    log = admin.get("/api/v1/audit-logs", params={"action": "telegram.chat_bound"}).json()["items"]
    assert log and log[0]["actor_login"] == "admin"


def test_bind_with_user_code_fails(user, container):
    code = user.post("/api/v1/telegram/link").json()["code"]
    c = send(container, msg(f"/bind {code}"))
    assert "Не получилось" in c.messages[0]["text"]


def bind(admin, container):
    link_system_admin(container)
    code = admin.post("/api/v1/telegram/chat-link").json()["command"]
    send(container, msg(code, tg_id=ADMIN_TG))


def test_topay_in_bound_chat_with_buttons(admin, user, container):
    bind(admin, container)
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-19")
    c = send(container, msg("/topay@InvoiceKeeperBot", tg_id=999))  # участник чата, не привязан
    text = c.messages[0]["text"]
    assert "Что и когда оплатить" in text and "Сервер" in text and "просрочено 5 дн." in text
    assert "Итого:" in text and "25,00\u00a0$" in text
    buttons = c.messages[0]["reply_markup"]["inline_keyboard"]
    assert buttons[0][0]["callback_data"].startswith("lp:")


def test_list_button_marks_paid_and_replies(admin, user, regular_user, container):
    bind(admin, container)
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": 555})
    p = create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    client = FakeTelegramClient()
    asyncio.run(
        TelegramUpdateHandler(container, client).handle_update(
            {"update_id": 5, "callback_query": {"id": "q", "from": {"id": 555}, "data": f"lp:{oid}",
                                                 "message": {"message_id": 3, "chat": {"id": GROUP}}}}
        )
    )
    assert client.edits == []  # список не редактируется
    assert "отметил(а) ivan" in client.messages[0]["text"] and client.messages[0]["reply_to"] == 3
    assert user.get(f"/api/v1/payment-occurrences/{oid}").json()["status"] == "paid"


def test_no_access_for_strangers(admin, container):
    create_payment(admin, first_due_date="2026-10-26")
    c = send(container, msg("/overdue", chat_id=-1, tg_id=1))
    assert "Нет доступа" in c.messages[0]["text"]


def test_free_text_questions_in_private(admin, regular_user, container):
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": 555})
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-19")
    c = send(container, msg("Что у нас просрочено?", chat_id=555, chat_type="private"))
    assert "Просрочено" in c.messages[0]["text"] and "Подписка" in c.messages[0]["text"]
    c = send(container, msg("покажи итоги", chat_id=555, chat_type="private"))
    assert "Итоги на 24.10.2026" in c.messages[0]["text"] and "EUR" in c.messages[0]["text"]
    c = send(container, msg("абракадабра", chat_id=555, chat_type="private"))
    assert "Не понял" in c.messages[0]["text"]


def test_paid_and_week_and_summary(admin, user, regular_user, container, clock):
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": 555})
    p = create_payment(admin, title="Аренда", amount="55000", first_due_date="2026-10-28")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    w = send(container, msg("/week", chat_id=555, chat_type="private")).messages[0]["text"]
    assert "Аренда" in w and "через 4 дн." in w
    user.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "paid"})
    pd = send(container, msg("/paid", chat_id=555, chat_type="private")).messages[0]["text"]
    assert "оплачено 24.10" in pd and "55\u00a0000,00\u00a0₽" in pd
    assert "55 000" not in pd
    sm = send(container, msg("/summary", chat_id=555, chat_type="private")).messages[0]["text"]
    assert "<b>RUB</b>" in sm and "USD" not in sm


def test_help(container):
    c = send(container, msg("/help", chat_id=1, chat_type="private"))
    assert "/topay" in c.messages[0]["text"]
