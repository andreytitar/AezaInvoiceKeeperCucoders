from __future__ import annotations

from pydantic import Field

from app.schemas.common import InputModel, OutputModel
from app.schemas.users import MeOut


class LoginRequest(InputModel):
    login: str = Field(min_length=1, max_length=64, examples=["admin"])
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(OutputModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    user: MeOut
