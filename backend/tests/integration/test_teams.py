"""Команды: изоляция, песочница из бота, magic-ссылка, приглашение, /bind, получатель напоминания, очистка."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.telegram import TelegramChannel
from app.models import NotificationDelivery, PaymentOccurrence, RecurringPayment, Team, TeamKind, User
from app.repositories.users import UserRepository
from app.services.reminders import ReminderService
from app.services.teams import SANDBOX_PER_MINUTE, TeamService
from app.services.telegram_updates import TelegramUpdateHandler
from tests.integration.helpers import create_payment, occurrences_of
from tests.worker.test_telegram_button import FakeTelegramClient
from tests.worker.test_telegram_bot import msg, send


def _sandbox(container, tg_id: int):
    with container.session_factory() as db:
        return TeamService(db, container.clock, container.settings).create_sandbox(tg_id)


def _magic(app, code: str) -> TestClient:
    client = TestClient(app)
    response = client.get(f"/api/v1/auth/magic/{code}", follow_redirects=False)
    assert response.status_code == 302, response.text
    assert "ik_session" in response.cookies
    client.cookies.set("ik_session", response.cookies["ik_session"])
    return client


def test_magic_link_once_and_employee_sees_same_team(admin, app, container):
    created = _sandbox(container, 4242)
    sand = _magic(app, created.admin_code)
    me = sand.get("/api/v1/auth/me").json()
    assert me["role"] == "admin" and me["team"]["kind"] == "sandbox" and me["is_system"] is False
    again = TestClient(app).get(f"/api/v1/auth/magic/{created.admin_code}", follow_redirects=False)
    assert again.status_code == 422

    employee = _magic(app, created.employee_code)
    emp = employee.get("/api/v1/auth/me").json()
    assert emp["role"] == "user" and emp["team"]["id"] == me["team"]["id"]
    assert employee.get("/api/v1/recurring-payments").json()
    assert employee.post("/api/v1/recurring-payments", json={
        "title": "Нельзя", "amount": "1.00", "currency": "RUB", "first_due_date": "2026-10-26",
    }).status_code == 403


def test_team_isolation_and_system_admin_untouchable(admin, app, container):
    created = _sandbox(container, 7777)
    sand = _magic(app, created.admin_code)
    create_payment(admin, title="Только основная", amount="10.00", currency="USD", first_due_date="2026-10-26")
    primary_titles = {p["title"] for p in admin.get("/api/v1/recurring-payments").json()}
    sandbox_titles = {p["title"] for p in sand.get("/api/v1/recurring-payments").json()}
    assert "Только основная" in primary_titles and "Сервер Aeza" not in primary_titles
    assert "Сервер Aeza" in sandbox_titles and "Аренда офиса" in sandbox_titles and "Только основная" not in sandbox_titles

    foreign = occurrences_of(admin, admin.get("/api/v1/recurring-payments").json()[0]["id"])[0]["id"]
    assert sand.get(f"/api/v1/payment-occurrences/{foreign}").status_code == 404
    assert sand.patch(f"/api/v1/payment-occurrences/{foreign}", json={"status": "paid"}).status_code == 404
    assert "Только основная" not in {i["title"] for i in sand.get("/api/v1/payment-occurrences").json()["items"]}

    sys_id = admin.get("/api/v1/auth/me").json()["id"]
    assert sand.patch(f"/api/v1/users/{sys_id}", json={"email": "a@b.co"}).status_code == 404
    assert sand.delete(f"/api/v1/users/{sys_id}").status_code == 404
    logins = {u["login"] for u in sand.get("/api/v1/users").json()}
    assert created.employee_login in logins and "admin" not in logins
    assert created.employee_login not in {u["login"] for u in admin.get("/api/v1/users").json()}


def test_start_paths_create_invite_and_bind(admin, app, container):
    stranger = send(container, msg("/start", chat_id=9001, tg_id=9001, chat_type="private"))
    buttons = [b["text"] for row in stranger.messages[0]["reply_markup"]["inline_keyboard"] for b in row]
    assert buttons == ["Создать временную команду", "Войти по коду приглашения", "Войти на сайте"]

    with container.session_factory() as db:
        ivan_id = UserRepository(db).get_by_login("admin").id
    # первичная привязка: системный админ уже в основной команде
    with container.session_factory() as db:
        UserRepository(db).get(ivan_id).telegram_user_id = 111
        db.commit()
    primary = send(container, msg("/start", chat_id=111, tg_id=111, chat_type="private"))
    assert "/topay" in primary.messages[0]["text"]
    assert "временн" not in primary.messages[0]["text"].lower()

    created = send(
        container,
        {
            "update_id": 2,
            "callback_query": {
                "id": "c1",
                "from": {"id": 2222},
                "data": "sb:new",
                "message": {"message_id": 1, "chat": {"id": 2222, "type": "private"}},
            },
        },
    )
    text = created.messages[0]["text"]
    assert "Открыть панель" in text and "Зайти как сотрудник" in text and "Пригласить" in text
    opened = send(container, msg("/start", chat_id=2222, tg_id=2222, chat_type="private", update_id=3))
    assert "Снова открыта" in opened.messages[0]["text"]
    assert "Зайти как сотрудник" in opened.messages[0]["text"]

    with container.session_factory() as db:
        code = db.scalar(select(Team.invite_code).where(Team.kind == TeamKind.SANDBOX))
    joined = send(container, msg(f"/join {code}", chat_id=3333, tg_id=3333, chat_type="private", update_id=4))
    assert "Вы в команде" in joined.messages[0]["text"]
    rejected = send(container, msg(f"/join {code}", chat_id=111, tg_id=111, chat_type="private", update_id=5))
    assert "Не получилось" in rejected.messages[0]["text"]

    bind_ask = send(
        container,
        {
            "update_id": 6,
            "callback_query": {
                "id": "c2",
                "from": {"id": 2222},
                "data": "sb:bind",
                "message": {"message_id": 2, "chat": {"id": 2222, "type": "private"}},
            },
        },
    )
    command = next(line for line in bind_ask.messages[0]["text"].splitlines() if line.startswith("/bind") or "/bind" in line)
    token = command.split()[-1].replace("</code>", "").replace("<code>", "")
    stranger_bind = send(container, msg(f"/bind {token}", chat_id=-100900, tg_id=3333, title="Чужая", update_id=7))
    assert "Не получилось" in stranger_bind.messages[0]["text"]

    # код уже сожжён неудачной попыткой — берём новый
    bind_ask = send(
        container,
        {
            "update_id": 8,
            "callback_query": {
                "id": "c3",
                "from": {"id": 2222},
                "data": "sb:bind",
                "message": {"message_id": 3, "chat": {"id": 2222, "type": "private"}},
            },
        },
    )
    token = bind_ask.messages[0]["text"].split("/bind ")[-1].split("<")[0].strip()
    primary_chat = int(container.settings.telegram_chat_id)
    denied = send(container, msg(f"/bind {token}", chat_id=primary_chat, tg_id=2222, title="Жюри", update_id=9))
    assert "основной чат" in denied.messages[0]["text"]

    bind_ask = send(
        container,
        {
            "update_id": 10,
            "callback_query": {
                "id": "c4",
                "from": {"id": 2222},
                "data": "sb:bind",
                "message": {"message_id": 4, "chat": {"id": 2222, "type": "private"}},
            },
        },
    )
    token = bind_ask.messages[0]["text"].split("/bind ")[-1].split("<")[0].strip()
    ok = send(container, msg(f"/bind {token}", chat_id=-100888, tg_id=2222, title="Песочница", update_id=11))
    assert "будут приходить в этот чат" in ok.messages[0]["text"]
    assert any(m["chat_id"] == 2222 and "Песочница" in m["text"] for m in ok.messages)

    other = _sandbox(container, 4444)
    with container.session_factory() as db:
        other_admin = UserRepository(db).get(other.admin_id)
        code_row = __import__("app.services.telegram_link", fromlist=["TelegramLinkService"]).TelegramLinkService(
            db, container.clock, container.settings
        ).create_chat_code(other_admin)
        other_code = code_row.code
    clash = send(container, msg(f"/bind {other_code}", chat_id=-100888, tg_id=4444, title="Вторая", update_id=12))
    assert "Не получилось" in clash.messages[0]["text"]


def test_reminder_recipient_is_team_chat_or_admin_dm(admin, container):
    created = _sandbox(container, 5151)
    create_payment(admin, title="Основной сервер", amount="3.00", currency="USD", first_due_date="2026-10-26")
    client = FakeTelegramClient()
    container.channels = ChannelRegistry([TelegramChannel(client, "-100500")])
    with container.session_factory() as db:
        ReminderService(db, container.clock, container.settings, container.channels).scan()
        rows = db.execute(
            select(NotificationDelivery.recipient, RecurringPayment.team_id)
            .join(PaymentOccurrence, PaymentOccurrence.id == NotificationDelivery.occurrence_id)
            .join(RecurringPayment, RecurringPayment.id == PaymentOccurrence.recurring_payment_id)
            .where(NotificationDelivery.channel == "telegram")
        ).all()
    by_team: dict = {}
    for recipient, team_id in rows:
        by_team.setdefault(str(team_id), set()).add(recipient)
    assert by_team[str(created.team_id)] == {"5151"}
    primary_id = admin.get("/api/v1/auth/me").json()["team"]["id"]
    assert by_team[primary_id] == {"-100500"}
    assert "-100500" not in by_team[str(created.team_id)]

    with container.session_factory() as db:
        team = db.get(Team, created.team_id)
        team.telegram_chat_id = -100777
        team.telegram_chat_title = "Группа песочницы"
        db.execute(delete(NotificationDelivery))
        db.commit()
        ReminderService(db, container.clock, container.settings, container.channels).scan()
        sand = {
            r
            for (r,) in db.execute(
                select(NotificationDelivery.recipient)
                .join(PaymentOccurrence, PaymentOccurrence.id == NotificationDelivery.occurrence_id)
                .join(RecurringPayment, RecurringPayment.id == PaymentOccurrence.recurring_payment_id)
                .where(NotificationDelivery.channel == "telegram", RecurringPayment.team_id == created.team_id)
            ).all()
        }
    assert sand == {"-100777"}


def test_expired_sandbox_is_deleted(admin, container):
    created = _sandbox(container, 6161)
    with container.session_factory() as db:
        team = db.get(Team, created.team_id)
        team.expires_at = container.clock.now() - timedelta(minutes=1)
        db.commit()
        assert TeamService(db, container.clock, container.settings).purge_expired() == 1
        assert db.get(Team, created.team_id) is None
        assert db.get(User, created.admin_id) is None
        assert db.scalar(select(RecurringPayment.id).where(RecurringPayment.team_id == created.team_id)) is None


def test_sandbox_creation_rate_limit(container):
    for i in range(SANDBOX_PER_MINUTE):
        _sandbox(container, 8000 + i)
    try:
        _sandbox(container, 8099)
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "too_many_requests"
    else:
        raise AssertionError("лимит песочниц не сработал")


def test_paid_button_requires_membership(admin, app, container):
    created = _sandbox(container, 7171)
    sand = _magic(app, created.admin_code)
    payment = next(p for p in sand.get("/api/v1/recurring-payments").json() if p["title"] == "Сервер Aeza")
    occ = occurrences_of(sand, payment["id"])[0]["id"]
    client = FakeTelegramClient()

    async def press(tg_id):
        await TelegramUpdateHandler(container, client).handle_update(
            {
                "update_id": tg_id,
                "callback_query": {
                    "id": f"q{tg_id}",
                    "from": {"id": tg_id},
                    "data": f"paid:{occ}",
                    "message": {"message_id": 1, "chat": {"id": -100777}},
                },
            }
        )

    asyncio.run(press(999001))
    assert client.answers[-1][2] is True
    assert sand.get(f"/api/v1/payment-occurrences/{occ}").json()["status"] == "unpaid"
    asyncio.run(press(7171))
    assert sand.get(f"/api/v1/payment-occurrences/{occ}").json()["status"] == "paid"
