"""Вход на сайт через Telegram.

Кнопка открывает t.me/<бот>?start=weblogin_<код>. Бот записывает telegram id в код,
сайт опрашивает его и повторяет развилку /start. Виджет Login Widget остаётся
запасным путём: подпись HMAC-SHA256, ключ — SHA256 токена бота.
Непривязанный id не становится сессией сам по себе.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.domain.clock import Clock
from app.domain.errors import Forbidden, NotFound, Unauthorized, ValidationError
from app.infrastructure.rate_limit import LoginRateLimiter
from app.models import Role, TeamKind, TelegramLinkCode, User
from app.repositories.users import UserRepository
from app.schemas.auth import TelegramWidgetAuth
from app.services.auth import AuthService, LoginResult
from app.services.teams import TeamService
from app.services.telegram_link import WEB_LOGIN_CODE, WEB_LOGIN_PURPOSE, TelegramLinkService

log = logging.getLogger("app.telegram.login")

WIDGET_MAX_AGE = timedelta(days=1)
PENDING_TTL = timedelta(minutes=15)


@dataclass
class TelegramIdentify:
    status: str
    login: LoginResult | None = None
    pending: str | None = None


def telegram_login_config(settings: Settings, resolved_username: str | None = None) -> tuple[bool, str | None, bool]:
    """enabled, имя бота, задан ли токен.

    resolved_username — имя из getMe, если в настройках его нет.
    enabled: по токену можно открыть ссылку t.me, то есть имя уже известно.
    """
    token_configured = bool(settings.telegram_bot_token)
    name = settings.telegram_login_bot or resolved_username
    return bool(token_configured and name), name, token_configured


def widget_fields(body: TelegramWidgetAuth) -> dict:
    data = body.model_dump()
    extra = body.model_extra or {}
    data.update(extra)
    return {key: value for key, value in data.items() if value is not None and not isinstance(value, (list, dict))}


def _canonical(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def data_check_string(fields: dict) -> str:
    lines = [f"{key}={_canonical(fields[key])}" for key in sorted(fields) if key != "hash"]
    return "\n".join(lines)


def verify_widget(fields: dict, bot_token: str | None, now: datetime) -> int:
    if not bot_token:
        raise Unauthorized("Вход через Telegram не настроен")
    received = fields.get("hash")
    if not isinstance(received, str) or len(received) != 64:
        raise Unauthorized("Подпись Telegram недействительна")
    secret = hashlib.sha256(bot_token.encode()).digest()
    digest = hmac.new(secret, data_check_string(fields).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, received):
        raise Unauthorized("Подпись Telegram недействительна")
    try:
        tg_id = int(fields["id"])
        auth_date = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError):
        raise Unauthorized("Подпись Telegram недействительна") from None
    if tg_id <= 0:
        raise Unauthorized("Подпись Telegram недействительна")
    now_ts = int(now.timestamp())
    if auth_date > now_ts + 60 or now_ts - auth_date > int(WIDGET_MAX_AGE.total_seconds()):
        raise Unauthorized("Данные входа Telegram устарели, войдите снова")
    return tg_id


def issue_pending(telegram_user_id: int, secret: str, now: datetime) -> str:
    exp = int((now + PENDING_TTL).timestamp())
    body = f"v1.{telegram_user_id}.{exp}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_pending(token: str | None, secret: str, now: datetime) -> int:
    if not token or token.count(".") != 3 or len(token) > 200:
        raise Unauthorized("Сначала войдите через Telegram")
    version, tg_s, exp_s, sig = token.split(".")
    body = f"{version}.{tg_s}.{exp_s}"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if version != "v1" or len(sig) != len(expected) or not hmac.compare_digest(expected, sig):
        raise Unauthorized("Сначала войдите через Telegram")
    try:
        tg_id = int(tg_s)
        exp = int(exp_s)
    except ValueError:
        raise Unauthorized("Сначала войдите через Telegram") from None
    if tg_id <= 0:
        raise Unauthorized("Сначала войдите через Telegram")
    if exp < int(now.timestamp()):
        raise Unauthorized("Время входа через Telegram истекло, войдите снова")
    return tg_id


class TelegramWebAuth:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings, limiter: LoginRateLimiter | None = None) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.auth = AuthService(db, clock, settings, limiter)
        self.users = UserRepository(db)

    def pending_id(self, token: str | None) -> int:
        return read_pending(token, self.settings.secret_key, self.clock.now())

    def has_pending(self, token: str | None) -> bool:
        try:
            self.pending_id(token)
        except Unauthorized:
            return False
        return True

    def identify(self, fields: dict) -> TelegramIdentify:
        return self.decide(verify_widget(fields, self.settings.telegram_bot_token, self.clock.now()))

    def decide(self, tg_id: int) -> TelegramIdentify:
        """Та же развилка, что у /start без кода: своя команда или экран выбора на сайте."""
        user = self.users.get_by_telegram_id(tg_id)
        if user is None:
            log.info("Telegram на сайте не привязан", extra={"telegram_user_id": tg_id})
            return TelegramIdentify(
                status="unlinked",
                pending=issue_pending(tg_id, self.settings.secret_key, self.clock.now()),
            )
        log.info("Вход через Telegram", extra={"telegram_user_id": tg_id, "login": user.login})
        return TelegramIdentify(status="authenticated", login=self.auth.start_session(user, "auth.telegram_login"))

    def poll_web_login(self, code: str | None) -> TelegramIdentify | None:
        """None — бот ещё не подтвердил Start. Иначе код сгорает и решается развилка /start."""
        if not code or not WEB_LOGIN_CODE.fullmatch(code):
            raise ValidationError("Сначала нажмите «Зайти через Telegram»")
        row = self.db.scalar(select(TelegramLinkCode).where(TelegramLinkCode.code == code).with_for_update())
        if row is None or row.purpose != WEB_LOGIN_PURPOSE:
            raise ValidationError("Ссылка входа недействительна")
        if row.used_at is not None:
            raise ValidationError("Ссылка входа уже использована")
        if row.expires_at < self.clock.now():
            raise ValidationError("Срок входа через Telegram истёк, нажмите кнопку ещё раз")
        if row.telegram_user_id is None:
            return None
        row.used_at = self.clock.now()
        result = self.decide(int(row.telegram_user_id))
        if result.login is None:
            self.db.commit()
        return result

    def create_sandbox(self, token: str | None) -> LoginResult:
        tg_id = self.pending_id(token)
        existing = self.users.get_by_telegram_id(tg_id)
        if existing is not None:
            return self.auth.start_session(existing, "auth.telegram_login")
        created = TeamService(self.db, self.clock, self.settings).create_sandbox(tg_id)
        admin = self.users.get(created.admin_id)
        if admin is None or admin.is_system:
            raise Unauthorized("Не удалось открыть временную команду")
        return self.auth.start_session(admin, "auth.telegram_login")

    def join(self, token: str | None, code: str) -> LoginResult:
        tg_id = self.pending_id(token)
        user = TeamService(self.db, self.clock, self.settings).join_by_invite(tg_id, code)
        user = self.users.get(user.id)
        if user is None or user.role != Role.USER or user.is_system:
            raise Unauthorized("Не удалось войти по коду приглашения")
        return self.auth.start_session(user, "auth.telegram_login")

    def link_account(self, token: str | None, login: str, password: str, ip: str) -> LoginResult:
        tg_id = self.pending_id(token)
        user = self.auth.authenticate_password(login, password, ip)
        TelegramLinkService(self.db, self.clock, self.settings).attach_telegram(user, tg_id)
        user = self.users.get(user.id)
        if user is None:
            raise Unauthorized("Не удалось привязать аккаунт")
        return self.auth.start_session(user, "auth.telegram_login")

    def enter_as_employee(self, actor: User) -> LoginResult:
        team = actor.team
        if actor.is_system or actor.role != Role.ADMIN or team is None or team.kind != TeamKind.SANDBOX:
            raise Forbidden("Войти как сотрудник может только администратор временной команды")
        employee = TeamService(self.db, self.clock, self.settings).employee_of(actor.team_id)
        if employee is None:
            raise NotFound("В этой команде нет учётной записи сотрудника")
        return self.auth.start_session(employee, "auth.sandbox_employee")
