from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SESSION_COOKIE, AuthDep, ContainerDep, DbDep, client_ip
from app.api.errors import responses
from app.schemas.auth import LoginRequest, LoginResponse, TokenResponse
from app.schemas.users import MeOut
from app.services.auth import AuthService

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
    return LoginResponse(access_token=result.token, user=MeOut.model_validate(result.user))


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
    return MeOut.model_validate(auth.user)


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
    return response
