from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import AdminDep, ContainerDep, DbDep
from app.api.errors import responses
from app.schemas.users import UserCreate, UserOut, UserUpdate
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut], summary="Пользователи (без системного админа)", responses=responses(401, 403))
def list_users(_: AdminDep, c: ContainerDep, db: DbDep) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in UserService(db, c.clock, c.settings).list()]


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя (роль всегда user)",
    responses=responses(401, 403, 409, 422),
)
def create_user(body: UserCreate, _: AdminDep, c: ContainerDep, db: DbDep) -> UserOut:
    user = UserService(db, c.clock, c.settings).create(**body.model_dump())
    return UserOut.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Изменить пользователя (смена пароля завершает его сессии)",
    responses=responses(401, 403, 404, 409, 422),
)
def update_user(user_id: uuid.UUID, body: UserUpdate, _: AdminDep, c: ContainerDep, db: DbDep) -> UserOut:
    fields = body.model_dump(exclude_unset=True)
    if "login" in fields and fields["login"] is None:
        fields.pop("login")
    if "password" in fields and fields["password"] is None:
        fields.pop("password")
    user = UserService(db, c.clock, c.settings).update(user_id, **fields)
    return UserOut.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить пользователя (сессии завершаются)",
    responses=responses(401, 403, 404),
)
def delete_user(user_id: uuid.UUID, _: AdminDep, c: ContainerDep, db: DbDep) -> Response:
    UserService(db, c.clock, c.settings).delete(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
