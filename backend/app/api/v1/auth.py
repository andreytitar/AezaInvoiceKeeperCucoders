from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    SESSION_COOKIE,
    TELEGRAM_PENDING_COOKIE,
    WEB_LOGIN_COOKIE,
    AuthDep,
    ContainerDep,
    DbDep,
    assert_browser_origin,
    client_ip,
)
from app.api.errors import responses
from app.api.v1.telegram import login_bot_username
from app.domain.errors import Unauthorized, ValidationError
from app.schemas.auth import (
    InviteCodeRequest,
    LoginRequest,
    LoginResponse,
    TelegramDeepLinkOut,
    TelegramLoginConfig,
    TelegramLoginResponse,
    TelegramPendingOut,
    TelegramWidgetAuth,
    TokenResponse,
)
from app.schemas.users import MeOut
from app.services.auth import AuthService
from app.services.telegram_link import WEB_LOGIN_PREFIX, WEB_LOGIN_TTL, TelegramLinkService
from app.services.telegram_login import PENDING_TTL, TelegramWebAuth, telegram_login_config, widget_fields

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str, c) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=c.settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=c.settings.cookie_secure,
        path="/",
    )


def _set_pending(response: Response, token: str, c) -> None:
    response.set_cookie(
        TELEGRAM_PENDING_COOKIE,
        token,
        max_age=int(PENDING_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=c.settings.cookie_secure,
        path="/",
    )


def _clear_pending(response: Response) -> None:
    response.delete_cookie(TELEGRAM_PENDING_COOKIE, path="/")


def _set_web_login(response: Response, code: str, c) -> None:
    response.set_cookie(
        WEB_LOGIN_COOKIE,
        code,
        max_age=int(WEB_LOGIN_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=c.settings.cookie_secure,
        path="/",
    )


def _clear_web_login(response: Response) -> None:
    response.delete_cookie(WEB_LOGIN_COOKIE, path="/")


def _session_response(result, response: Response, c) -> LoginResponse:
    _set_cookie(response, result.token, c)
    _clear_pending(response)
    return LoginResponse(access_token=result.token, user=MeOut.from_user(result.user))


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Вход по логину и паролю",
    description="Устанавливает HttpOnly-cookie сессии и возвращает тот же токен для `Authorization: Bearer`.",
    responses={**responses(401, 422), 429: {"description": "Слишком много попыток"}},
)
def login(body: LoginRequest, request: Request, response: Response, c: ContainerDep, db: DbDep) -> LoginResponse:
    result = AuthService(db, c.clock, c.settings, c.rate_limiter).login(body.login, body.password, client_ip(request))
    _set_cookie(response, result.token, c)
    return LoginResponse(access_token=result.token, user=MeOut.from_user(result.user))


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Токен для кнопки Authorize в Swagger (OAuth2 password flow)",
    responses={**responses(401), 429: {"description": "Слишком много попыток"}},
)
def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, c: ContainerDep, db: DbDep
) -> TokenResponse:
    result = AuthService(db, c.clock, c.settings, c.rate_limiter).login(form.username, form.password, client_ip(request))
    return TokenResponse(access_token=result.token)


@router.get("/me", response_model=MeOut, summary="Текущий пользователь", responses=responses(401))
def me(auth: AuthDep) -> MeOut:
    return MeOut.from_user(auth.user)


@router.get(
    "/magic/{code}",
    summary="Вход по одноразовой ссылке из бота",
    description="Ставит ту же HttpOnly-сессию, что и обычный вход, и перенаправляет в панель. Ссылка сгорает после первого открытия.",
    responses=responses(422),
)
def magic_login(code: str, c: ContainerDep, db: DbDep) -> RedirectResponse:
    result = AuthService(db, c.clock, c.settings).login_magic(code)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _set_cookie(response, result.token, c)
    return response


@router.get(
    "/telegram/config",
    response_model=TelegramLoginConfig,
    summary="Настроена ли кнопка входа через Telegram",
    description="Если имя бота в настройках пустое, а токен задан, имя запрашивается у Telegram (getMe) и кэшируется.",
)
async def telegram_config(c: ContainerDep) -> TelegramLoginConfig:
    resolved = await login_bot_username(c) if c.settings.telegram_bot_token and not c.settings.telegram_login_bot else None
    enabled, name, token_configured = telegram_login_config(c.settings, resolved)
    return TelegramLoginConfig(enabled=enabled, bot_username=name, token_configured=token_configured)


@router.post(
    "/telegram/deeplink",
    response_model=TelegramDeepLinkOut,
    summary="Ссылка t.me для входа через бота",
    description=(
        "Создаёт одноразовый код на 10 минут и кладёт его в HttpOnly-cookie. "
        "Ссылка открывает бота с /start weblogin_<код>. Домен и HTTPS не нужны."
    ),
    responses=responses(401, 422),
)
async def telegram_deeplink(request: Request, response: Response, c: ContainerDep, db: DbDep) -> TelegramDeepLinkOut:
    assert_browser_origin(request)
    if not c.settings.telegram_bot_token:
        raise Unauthorized("Вход через Telegram не настроен")
    name = await login_bot_username(c)
    if not name:
        raise ValidationError("Не удалось подготовить вход через Telegram. Попробуйте ещё раз.")
    row = TelegramLinkService(db, c.clock, c.settings).create_web_login()
    _set_web_login(response, row.code, c)
    return TelegramDeepLinkOut(
        code=row.code,
        url=f"https://t.me/{name}?start={WEB_LOGIN_PREFIX}{row.code}",
        expires_at=row.expires_at,
    )


@router.post(
    "/telegram/deeplink/status",
    response_model=TelegramLoginResponse,
    summary="Опрос подтверждения входа через бота",
    description=(
        "Пока пользователь не нажал Start, статус waiting. После Start — та же развилка, что у /start: "
        "привязанный Telegram получает HttpOnly-сессию, непривязанный — экран выбора на сайте."
    ),
    responses=responses(422),
)
def telegram_deeplink_status(request: Request, response: Response, c: ContainerDep, db: DbDep) -> TelegramLoginResponse:
    assert_browser_origin(request)
    found = TelegramWebAuth(db, c.clock, c.settings, c.rate_limiter).poll_web_login(
        request.cookies.get(WEB_LOGIN_COOKIE)
    )
    if found is None:
        return TelegramLoginResponse(status="waiting")
    if found.status == "authenticated" and found.login is not None:
        _set_cookie(response, found.login.token, c)
        _clear_pending(response)
        return TelegramLoginResponse(
            status="authenticated",
            access_token=found.login.token,
            user=MeOut.from_user(found.login.user),
        )
    if found.pending:
        _set_pending(response, found.pending, c)
    return TelegramLoginResponse(status="unlinked")


@router.get(
    "/telegram/pending",
    response_model=TelegramPendingOut,
    summary="Есть ли незавершённый вход через Telegram",
    description="После виджета, если аккаунт ещё не привязан, браузер хранит HttpOnly-cookie. Сессии панели при этом нет.",
)
def telegram_pending(request: Request, c: ContainerDep, db: DbDep) -> TelegramPendingOut:
    pending = TelegramWebAuth(db, c.clock, c.settings).has_pending(request.cookies.get(TELEGRAM_PENDING_COOKIE))
    return TelegramPendingOut(pending=pending)


@router.post(
    "/telegram",
    response_model=TelegramLoginResponse,
    summary="Вход по Telegram Login Widget",
    description=(
        "Проверяет hash виджета (HMAC-SHA256, секрет — SHA256 токена бота) и отвергает auth_date старше суток. "
        "Привязанный Telegram открывает сессию этого пользователя. Непривязанный получает статус unlinked "
        "и может создать временную команду, ввести код приглашения или привязать существующий логин."
    ),
    responses=responses(401, 422),
)
def telegram_login(
    body: TelegramWidgetAuth, request: Request, response: Response, c: ContainerDep, db: DbDep
) -> TelegramLoginResponse:
    assert_browser_origin(request)
    found = TelegramWebAuth(db, c.clock, c.settings, c.rate_limiter).identify(widget_fields(body))
    if found.status == "authenticated" and found.login is not None:
        _set_cookie(response, found.login.token, c)
        _clear_pending(response)
        return TelegramLoginResponse(
            status="authenticated",
            access_token=found.login.token,
            user=MeOut.from_user(found.login.user),
        )
    if found.pending:
        _set_pending(response, found.pending, c)
    return TelegramLoginResponse(status="unlinked")


@router.post(
    "/telegram/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Забыть незавершённый вход через Telegram",
)
def telegram_cancel(request: Request) -> Response:
    assert_browser_origin(request)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_pending(response)
    return response


@router.post(
    "/telegram/sandbox",
    response_model=LoginResponse,
    summary="Создать временную команду и войти её администратором",
    description="Тот же TeamService, что и кнопка бота «Создать временную команду»: администратор, сотрудник, демо-платежи, 24 часа.",
    responses={**responses(401, 409, 422), 429: {"description": "Слишком много временных команд"}},
)
def telegram_sandbox(request: Request, response: Response, c: ContainerDep, db: DbDep) -> LoginResponse:
    assert_browser_origin(request)
    result = TelegramWebAuth(db, c.clock, c.settings, c.rate_limiter).create_sandbox(
        request.cookies.get(TELEGRAM_PENDING_COOKIE)
    )
    return _session_response(result, response, c)


@router.post(
    "/telegram/join",
    response_model=LoginResponse,
    summary="Войти по коду приглашения временной команды",
    description="Те же правила, что у /join в боте: код песочницы, срок, один Telegram — одна команда. Роль нового участника — user.",
    responses=responses(401, 409, 422),
)
def telegram_join(body: InviteCodeRequest, request: Request, response: Response, c: ContainerDep, db: DbDep) -> LoginResponse:
    assert_browser_origin(request)
    result = TelegramWebAuth(db, c.clock, c.settings, c.rate_limiter).join(
        request.cookies.get(TELEGRAM_PENDING_COOKIE), body.code
    )
    return _session_response(result, response, c)


@router.post(
    "/telegram/link",
    response_model=LoginResponse,
    summary="Привязать Telegram к уже существующему логину",
    description=(
        "Пароль проверяется как при обычном входе, затем Telegram id из виджета записывается в этот профиль. "
        "Новый администратор основной команды не создаётся."
    ),
    responses={**responses(401, 409, 422), 429: {"description": "Слишком много попыток"}},
)
def telegram_link_account(
    body: LoginRequest, request: Request, response: Response, c: ContainerDep, db: DbDep
) -> LoginResponse:
    assert_browser_origin(request)
    result = TelegramWebAuth(db, c.clock, c.settings, c.rate_limiter).link_account(
        request.cookies.get(TELEGRAM_PENDING_COOKIE), body.login, body.password, client_ip(request)
    )
    return _session_response(result, response, c)


@router.post(
    "/sandbox/employee",
    response_model=LoginResponse,
    summary="Зайти как сотрудник временной команды",
    description="Сменяет сессию администратора песочницы на заранее созданного сотрудника той же команды.",
    responses=responses(401, 403, 404),
)
def sandbox_employee(auth: AuthDep, response: Response, c: ContainerDep, db: DbDep) -> LoginResponse:
    result = TelegramWebAuth(db, c.clock, c.settings, c.rate_limiter).enter_as_employee(auth.user)
    return _session_response(result, response, c)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход: сессия инвалидируется на сервере",
    responses=responses(401),
)
def logout(auth: AuthDep, c: ContainerDep, db: DbDep) -> Response:
    AuthService(db, c.clock, c.settings).logout(auth.session)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    _clear_pending(response)
    _clear_web_login(response)
    return response
