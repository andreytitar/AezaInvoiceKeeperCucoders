"""Вход на сайт через Telegram Login Widget: та же развилка, что /start у бота."""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.v1.telegram import _bot_cache
from app.infrastructure.channels.telegram import TelegramClient, TelegramError
from app.models import Team, TeamKind, TelegramLinkCode, User
from app.repositories.users import UserRepository
from app.services.teams import TeamService
from tests.conftest import ADMIN_LOGIN
from tests.integration.conftest import USER_PASSWORD
from tests.integration.helpers import create_payment, occurrences_of
from tests.worker.test_telegram_bot import msg, send

BOT = "123456:fake-bot-token"
BOT_NAME = "invoice_keeper_bot"


def _enable(container, *, token: str | None = BOT, username: str | None = BOT_NAME) -> None:
    container.settings.telegram_bot_token = token
    container.settings.telegram_bot_username = username


def _auth_date(container, *, skew: int = 0) -> int:
    return int(container.clock.now().timestamp()) + skew


def widget(tg_id: int, auth_date: int, *, first_name: str = "Анна", **extra: str) -> dict:
    fields = {"auth_date": str(auth_date), "first_name": first_name, "id": str(tg_id)}
    fields.update(extra)
    secret = hashlib.sha256(BOT.encode()).digest()
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    body: dict = {"id": tg_id, "auth_date": auth_date, "first_name": first_name, "hash": digest}
    body.update(extra)
    return body


def _sandbox_count(container) -> int:
    with container.session_factory() as db:
        return int(db.scalar(select(func.count()).select_from(Team).where(Team.kind == TeamKind.SANDBOX)) or 0)


def _system_admins(container) -> list[str]:
    with container.session_factory() as db:
        rows = db.scalars(select(User.login).where(User.is_system.is_(True), User.deleted_at.is_(None))).all()
        return list(rows)


def _set_telegram(container, login: str, tg_id: int | None) -> None:
    with container.session_factory() as db:
        user = UserRepository(db).get_by_login(login)
        assert user is not None
        user.telegram_user_id = tg_id
        db.commit()


def _cookie(response, name: str) -> str | None:
    for raw in response.headers.get_list("set-cookie"):
        if raw.lower().startswith(name.lower() + "="):
            return raw
    return None


def test_config_hidden_until_bot_username_and_token(anon, container):
    off = anon.get("/api/v1/auth/telegram/config")
    assert off.status_code == 200
    assert off.json() == {"enabled": False, "bot_username": None, "token_configured": False}
    _enable(container, username="@invoice_keeper_bot")
    on = anon.get("/api/v1/auth/telegram/config")
    assert on.json() == {"enabled": True, "bot_username": BOT_NAME, "token_configured": True}
    _enable(container, token=None, username=BOT_NAME)
    partial = anon.get("/api/v1/auth/telegram/config").json()
    assert partial["enabled"] is False
    assert partial["bot_username"] == BOT_NAME
    assert partial["token_configured"] is False


def test_invalid_hash_and_stale_auth_date_rejected(anon, container):
    _enable(container)
    forged = widget(501, _auth_date(container))
    forged["hash"] = "0" * 64
    bad = anon.post("/api/v1/auth/telegram", json=forged)
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthorized"
    assert _sandbox_count(container) == 0

    tampered = widget(501, _auth_date(container))
    tampered["id"] = 502
    assert anon.post("/api/v1/auth/telegram", json=tampered).status_code == 401

    stale = widget(501, _auth_date(container, skew=-(24 * 3600 + 30)))
    old = anon.post("/api/v1/auth/telegram", json=stale)
    assert old.status_code == 401
    assert "устар" in old.json()["error"]["message"]

    _enable(container, token=None)
    missing = anon.post("/api/v1/auth/telegram", json=widget(501, _auth_date(container)))
    assert missing.status_code == 401
    assert "не настроен" in missing.json()["error"]["message"]
    assert _system_admins(container) == [ADMIN_LOGIN]


def test_unlinked_widget_then_create_sandbox(anon, app, container, admin):
    _enable(container)
    create_payment(admin, title="Только основная", amount="10.00", currency="USD", first_due_date="2026-10-26")
    identified = anon.post("/api/v1/auth/telegram", json=widget(555001, _auth_date(container)))
    assert identified.status_code == 200
    body = identified.json()
    assert body["status"] == "unlinked" and body["user"] is None and body["access_token"] is None
    pending = _cookie(identified, "ik_tg_pending")
    assert pending and "httponly" in pending.lower() and "samesite=lax" in pending.lower()
    assert _cookie(identified, "ik_session") is None
    assert _sandbox_count(container) == 0
    assert anon.get("/api/v1/auth/telegram/pending").json()["pending"] is True

    created = anon.post("/api/v1/auth/telegram/sandbox")
    assert created.status_code == 200, created.text
    me = created.json()["user"]
    assert me["role"] == "admin" and me["team"]["kind"] == "sandbox" and me["is_system"] is False
    assert me["login"] != ADMIN_LOGIN and me["telegram_user_id"] == 555001 and me["invite_code"]
    session = _cookie(created, "ik_session")
    assert session and "httponly" in session.lower()
    assert anon.get("/api/v1/auth/me").json()["id"] == me["id"]
    payments = anon.get("/api/v1/recurring-payments").json()
    assert {p["title"] for p in payments} == {"Аренда офиса", "Сервер Aeza", "Подписка JetBrains"}
    assert {p["currency"] for p in payments} == {"RUB", "USD", "EUR"}
    assert "Только основная" not in {p["title"] for p in payments}
    assert "Сервер Aeza" not in {p["title"] for p in admin.get("/api/v1/recurring-payments").json()}
    foreign = occurrences_of(admin, admin.get("/api/v1/recurring-payments").json()[0]["id"])[0]["id"]
    assert anon.get(f"/api/v1/payment-occurrences/{foreign}").status_code == 404
    with container.session_factory() as db:
        team = db.get(Team, me["team"]["id"])
        assert team.telegram_chat_id is None
    assert _system_admins(container) == [ADMIN_LOGIN]
    assert _sandbox_count(container) == 1

    again = TestClient(app).post("/api/v1/auth/telegram", json=widget(555001, _auth_date(container)))
    assert again.status_code == 200
    assert again.json()["status"] == "authenticated"
    assert again.json()["user"]["team"]["id"] == me["team"]["id"]
    assert _sandbox_count(container) == 1


def test_linked_primary_user_gets_session_without_sandbox(anon, container):
    _enable(container)
    _set_telegram(container, ADMIN_LOGIN, 42)
    before = _sandbox_count(container)
    response = anon.post("/api/v1/auth/telegram", json=widget(42, _auth_date(container)))
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert response.json()["status"] == "authenticated"
    assert user["login"] == ADMIN_LOGIN and user["is_system"] is True and user["team"]["kind"] == "primary"
    assert user["invite_code"] is None
    assert _sandbox_count(container) == before
    assert anon.get("/api/v1/auth/me").json()["login"] == ADMIN_LOGIN


def test_linked_sandbox_user_returns_to_same_team(anon, container):
    _enable(container)
    with container.session_factory() as db:
        created = TeamService(db, container.clock, container.settings).create_sandbox(77)
    response = anon.post("/api/v1/auth/telegram", json=widget(77, _auth_date(container)))
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert response.json()["status"] == "authenticated"
    assert user["team"]["id"] == str(created.team_id) and user["team"]["kind"] == "sandbox"
    assert user["role"] == "admin" and user["is_system"] is False
    assert _sandbox_count(container) == 1
    anon.post("/api/v1/auth/telegram", json=widget(77, _auth_date(container)))
    assert _sandbox_count(container) == 1


def test_join_code_matches_bot_rules(anon, app, container, admin, regular_user):
    assert regular_user.login == "ivan"
    _enable(container)
    create_payment(admin, title="Только основная", amount="10.00", currency="USD", first_due_date="2026-10-26")
    with container.session_factory() as db:
        created = TeamService(db, container.clock, container.settings).create_sandbox(1000)
    assert anon.post("/api/v1/auth/telegram/join", json={"code": created.invite_code}).status_code == 401

    identified = anon.post("/api/v1/auth/telegram", json=widget(2000, _auth_date(container)))
    assert identified.json()["status"] == "unlinked"
    wrong = anon.post("/api/v1/auth/telegram/join", json={"code": "NO-SUCH"})
    assert wrong.status_code == 422
    assert wrong.json()["error"]["message"] == "Код приглашения не найден"
    assert anon.get("/api/v1/auth/me").status_code == 401

    joined = anon.post("/api/v1/auth/telegram/join", json={"code": created.invite_code.lower()})
    assert joined.status_code == 200, joined.text
    member = joined.json()["user"]
    assert member["role"] == "user" and member["is_system"] is False
    assert member["team"]["id"] == str(created.team_id) and member["telegram_user_id"] == 2000
    titles = {p["title"] for p in anon.get("/api/v1/recurring-payments").json()}
    assert "Сервер Aeza" in titles and "Только основная" not in titles
    assert _system_admins(container) == [ADMIN_LOGIN]

    taken = TestClient(app)
    assert taken.post("/api/v1/auth/telegram", json=widget(3000, _auth_date(container))).json()["status"] == "unlinked"
    _set_telegram(container, "ivan", 3000)
    conflict = taken.post("/api/v1/auth/telegram/join", json={"code": created.invite_code})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "telegram_taken"

    expired = TestClient(app)
    assert expired.post("/api/v1/auth/telegram", json=widget(4000, _auth_date(container))).json()["status"] == "unlinked"
    with container.session_factory() as db:
        team = db.get(Team, created.team_id)
        team.expires_at = container.clock.now() - timedelta(seconds=1)
        db.commit()
    late = expired.post("/api/v1/auth/telegram/join", json={"code": created.invite_code})
    assert late.status_code == 422
    assert late.json()["error"]["message"] == "Срок временной команды истёк"


def test_sandbox_employee_switch_and_primary_admin_cannot(anon, app, container, admin):
    _enable(container)
    create_payment(admin, title="Только основная", amount="3.00", currency="EUR", first_due_date="2026-10-26")
    anon.post("/api/v1/auth/telegram", json=widget(6006, _auth_date(container)))
    opened = anon.post("/api/v1/auth/telegram/sandbox")
    assert opened.status_code == 200, opened.text
    team_id = opened.json()["user"]["team"]["id"]
    assert TestClient(app).post("/api/v1/auth/sandbox/employee").status_code == 401
    denied = admin.post("/api/v1/auth/sandbox/employee")
    assert denied.status_code == 403
    assert admin.get("/api/v1/auth/me").json()["is_system"] is True

    switched = anon.post("/api/v1/auth/sandbox/employee")
    assert switched.status_code == 200, switched.text
    employee = switched.json()["user"]
    assert employee["role"] == "user" and employee["login"].startswith("sotrudnik")
    assert employee["team"]["id"] == team_id and employee["invite_code"] is None
    assert employee["telegram_user_id"] is None and employee["is_system"] is False
    assert anon.get("/api/v1/auth/me").json()["role"] == "user"
    titles = {p["title"] for p in anon.get("/api/v1/recurring-payments").json()}
    assert "Сервер Aeza" in titles and "Только основная" not in titles
    assert anon.post("/api/v1/recurring-payments", json={
        "title": "Нельзя", "amount": "1.00", "currency": "RUB", "first_due_date": "2026-10-26",
    }).status_code == 403
    assert anon.post("/api/v1/auth/sandbox/employee").status_code == 403
    assert anon.post("/api/v1/telegram/chat-link").status_code == 403


def test_link_existing_account_does_not_create_admin(anon, app, container, regular_user):
    assert regular_user.login == "ivan"
    _enable(container)
    before = _system_admins(container)
    anon.post("/api/v1/auth/telegram", json=widget(7007, _auth_date(container)))
    bad = anon.post("/api/v1/auth/telegram/link", json={"login": "ivan", "password": "wrong-pass"})
    assert bad.status_code == 401
    with container.session_factory() as db:
        assert UserRepository(db).get_by_login("ivan").telegram_user_id is None

    linked = anon.post("/api/v1/auth/telegram/link", json={"login": "ivan", "password": USER_PASSWORD})
    assert linked.status_code == 200, linked.text
    user = linked.json()["user"]
    assert user["login"] == "ivan" and user["role"] == "user" and user["is_system"] is False
    assert user["team"]["kind"] == "primary" and user["telegram_user_id"] == 7007
    assert _system_admins(container) == before
    assert anon.get("/api/v1/auth/me").json()["login"] == "ivan"

    other = TestClient(app)
    other.post("/api/v1/auth/telegram", json=widget(7008, _auth_date(container)))
    with container.session_factory() as db:
        TeamService(db, container.clock, container.settings).create_sandbox(7008)
    clash = other.post("/api/v1/auth/telegram/link", json={"login": "ivan", "password": USER_PASSWORD})
    assert clash.status_code == 409
    assert anon.get("/api/v1/auth/me").json()["telegram_user_id"] == 7007


def test_pending_expires_and_forged_cookie_rejected(app, container, clock):
    _enable(container)
    forged = TestClient(app)
    forged.cookies.set("ik_tg_pending", "v1.8080.9999999999." + ("ab" * 32), domain="testserver", path="/")
    rejected = forged.post("/api/v1/auth/telegram/sandbox")
    assert rejected.status_code == 401
    assert "Сначала войдите" in rejected.json()["error"]["message"]

    anon = TestClient(app)
    assert anon.post("/api/v1/auth/telegram", json=widget(8080, _auth_date(container))).json()["status"] == "unlinked"
    clock.advance(minutes=16)
    late = anon.post("/api/v1/auth/telegram/sandbox")
    assert late.status_code == 401
    assert "истекло" in late.json()["error"]["message"]
    assert _sandbox_count(container) == 0


def _web_login(client) -> str:
    created = client.post("/api/v1/auth/telegram/deeplink")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["url"] == f"https://t.me/{BOT_NAME}?start=weblogin_{body['code']}"
    raw = _cookie(created, "ik_tg_web")
    assert raw and "httponly" in raw.lower() and "samesite=lax" in raw.lower()
    return body["code"]


def _press_start(container, code: str, tg_id: int, update_id: int = 1):
    return send(
        container,
        msg(
            f"/start weblogin_{code}",
            chat_id=tg_id,
            tg_id=tg_id,
            chat_type="private",
            update_id=update_id,
        ),
    )


def test_deeplink_requires_token(anon, container):
    _enable(container, token=None, username=BOT_NAME)
    denied = anon.post("/api/v1/auth/telegram/deeplink")
    assert denied.status_code == 401
    assert "не настроен" in denied.json()["error"]["message"]


def test_config_uses_get_me_when_username_missing(anon, container, monkeypatch):
    _enable(container, username=None)
    _bot_cache.clear()

    async def fake_get_me(self):
        return {"id": 1, "username": "resolved_keeper_bot"}

    monkeypatch.setattr(TelegramClient, "get_me", fake_get_me)
    cfg = anon.get("/api/v1/auth/telegram/config").json()
    assert cfg["enabled"] is True and cfg["token_configured"] is True
    assert cfg["bot_username"] == "resolved_keeper_bot"
    created = anon.post("/api/v1/auth/telegram/deeplink")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["url"] == f"https://t.me/resolved_keeper_bot?start=weblogin_{body['code']}"
    assert "Имя бота" not in created.text


def test_get_me_failure_does_not_say_username_missing(anon, container, monkeypatch):
    _enable(container, username=None)
    _bot_cache.clear()

    async def fake_get_me(self):
        raise TelegramError("getMe: недоступен")

    monkeypatch.setattr(TelegramClient, "get_me", fake_get_me)
    cfg = anon.get("/api/v1/auth/telegram/config").json()
    assert cfg == {"enabled": False, "bot_username": None, "token_configured": True}
    failed = anon.post("/api/v1/auth/telegram/deeplink")
    assert failed.status_code == 422
    assert "не задано" not in failed.json()["error"]["message"]
    assert "Имя бота" not in failed.text


def test_config_skips_get_me_when_username_configured(anon, container, monkeypatch):
    _enable(container)

    async def boom(self):
        raise AssertionError("getMe")

    monkeypatch.setattr(TelegramClient, "get_me", boom)
    cfg = anon.get("/api/v1/auth/telegram/config").json()
    assert cfg["bot_username"] == BOT_NAME and cfg["enabled"] is True


def test_deeplink_unlinked_poll_opens_choice_and_sandbox(anon, container):
    _enable(container)
    code = _web_login(anon)
    waiting = anon.post("/api/v1/auth/telegram/deeplink/status")
    assert waiting.status_code == 200
    assert waiting.json()["status"] == "waiting" and waiting.json()["user"] is None
    assert _cookie(waiting, "ik_session") is None
    assert _sandbox_count(container) == 0

    bot = _press_start(container, code, 555001)
    assert "подтверждён" in bot.messages[0]["text"]
    polled = anon.post("/api/v1/auth/telegram/deeplink/status")
    assert polled.status_code == 200, polled.text
    assert polled.json()["status"] == "unlinked" and polled.json()["user"] is None
    pending = _cookie(polled, "ik_tg_pending")
    assert pending and "httponly" in pending.lower()
    assert _cookie(polled, "ik_session") is None

    created = anon.post("/api/v1/auth/telegram/sandbox")
    assert created.status_code == 200, created.text
    me = created.json()["user"]
    assert me["telegram_user_id"] == 555001 and me["team"]["kind"] == "sandbox" and me["role"] == "admin"
    assert _cookie(created, "ik_session") and "httponly" in _cookie(created, "ik_session").lower()


def test_deeplink_existing_primary_user_gets_session(anon, container):
    _enable(container)
    _set_telegram(container, ADMIN_LOGIN, 42)
    before = _sandbox_count(container)
    code = _web_login(anon)
    _press_start(container, code, 42)
    polled = anon.post("/api/v1/auth/telegram/deeplink/status")
    assert polled.status_code == 200, polled.text
    user = polled.json()["user"]
    assert polled.json()["status"] == "authenticated"
    assert user["login"] == ADMIN_LOGIN and user["is_system"] is True and user["team"]["kind"] == "primary"
    session = _cookie(polled, "ik_session")
    assert session and "httponly" in session.lower()
    assert anon.get("/api/v1/auth/me").json()["login"] == ADMIN_LOGIN
    assert _sandbox_count(container) == before


def test_deeplink_existing_sandbox_user_gets_session(anon, container):
    _enable(container)
    with container.session_factory() as db:
        created = TeamService(db, container.clock, container.settings).create_sandbox(77)
    code = _web_login(anon)
    _press_start(container, code, 77)
    polled = anon.post("/api/v1/auth/telegram/deeplink/status")
    assert polled.status_code == 200, polled.text
    user = polled.json()["user"]
    assert polled.json()["status"] == "authenticated"
    assert user["team"]["id"] == str(created.team_id) and user["team"]["kind"] == "sandbox"
    assert user["role"] == "admin" and user["is_system"] is False
    assert _sandbox_count(container) == 1


def test_deeplink_expired_and_reused_rejected(app, container, clock):
    _enable(container)
    anon = TestClient(app)
    code = _web_login(anon)
    clock.advance(minutes=11)
    late = anon.post("/api/v1/auth/telegram/deeplink/status")
    assert late.status_code == 422
    assert "истёк" in late.json()["error"]["message"]
    expired_bot = _press_start(container, code, 4242)
    assert "истёк" in expired_bot.messages[0]["text"]
    with container.session_factory() as db:
        assert UserRepository(db).get_by_telegram_id(4242) is None
        row = db.get(TelegramLinkCode, code)
        assert row.telegram_user_id is None and row.used_at is None

    _set_telegram(container, ADMIN_LOGIN, 42)
    fresh = TestClient(app)
    code2 = _web_login(fresh)
    confirmed = _press_start(container, code2, 42, update_id=2)
    assert "подтверждён" in confirmed.messages[0]["text"]
    first = fresh.post("/api/v1/auth/telegram/deeplink/status")
    assert first.status_code == 200 and first.json()["status"] == "authenticated"
    again = fresh.post("/api/v1/auth/telegram/deeplink/status")
    assert again.status_code == 422
    assert "уже использована" in again.json()["error"]["message"]
    reused = send(
        container,
        msg(f"/start weblogin_{code2}", chat_id=99, tg_id=99, chat_type="private", update_id=3),
    )
    assert "уже использована" in reused.messages[0]["text"]
    with container.session_factory() as db:
        row = db.get(TelegramLinkCode, code2)
        assert row.telegram_user_id == 42 and row.used_at is not None
        assert UserRepository(db).get_by_telegram_id(99) is None


def test_web_login_invalid_payload_ignored(container, user):
    _enable(container)
    for update_id, text in enumerate(
        (
            "/start weblogin_",
            "/start weblogin_not-a-code",
            "/start weblogin_0123456789abcdef",
            "/start weblogin_DEADBEEFDEADBEEF",
        ),
        start=1,
    ):
        client = send(container, msg(text, chat_id=4242, tg_id=4242, chat_type="private", update_id=update_id))
        answer = client.messages[0]["text"]
        assert "привязан" not in answer
        assert "Код не найден" not in answer
    with container.session_factory() as db:
        assert UserRepository(db).get_by_telegram_id(4242) is None
    plain = send(container, msg("/start", chat_id=4242, tg_id=4242, chat_type="private", update_id=10))
    assert "ещё не привязан" in plain.messages[0]["text"]
    group = send(
        container,
        msg("/start weblogin_0123456789abcdef", chat_id=-100777, tg_id=1, chat_type="supergroup", update_id=11),
    )
    assert "только в личке" in group.messages[0]["text"]

    link = user.post("/api/v1/telegram/link").json()
    wrapped = send(
        container,
        msg(f"/start weblogin_{link['code']}", chat_id=555, tg_id=555, chat_type="private", update_id=12),
    )
    assert "привязан к пользователю" not in wrapped.messages[0]["text"]
    assert user.get("/api/v1/auth/me").json()["telegram_user_id"] is None
    real = send(container, msg(link["command"], chat_id=555, tg_id=555, chat_type="private", update_id=13))
    assert "Telegram привязан к <b>ivan</b>" in real.messages[0]["text"]
    assert user.get("/api/v1/auth/me").json()["telegram_user_id"] == 555


def test_magic_link_still_opens_session(app, container):
    with container.session_factory() as db:
        created = TeamService(db, container.clock, container.settings).create_sandbox(9090)
    client = TestClient(app)
    response = client.get(f"/api/v1/auth/magic/{created.admin_code}", follow_redirects=False)
    assert response.status_code == 302
    assert "ik_session" in response.cookies
    client.cookies.set("ik_session", response.cookies["ik_session"])
    me = client.get("/api/v1/auth/me").json()
    assert me["team"]["kind"] == "sandbox" and me["is_system"] is False
