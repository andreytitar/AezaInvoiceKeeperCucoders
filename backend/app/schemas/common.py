from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class InputModel(BaseModel):
    """Базовая модель входных данных: неизвестные поля запрещены (422)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
