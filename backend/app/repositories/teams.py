"""Команды: одна основная и временные песочницы."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import Team, TeamKind


class TeamRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get(self, team_id: uuid.UUID) -> Team | None:
        return self.db.get(Team, team_id)

    def get_primary(self) -> Team | None:
        return self.db.scalar(select(Team).where(Team.kind == TeamKind.PRIMARY))

    def ensure_primary(self) -> Team:
        row = self.get_primary()
        if row is not None:
            return row
        row = Team(kind=TeamKind.PRIMARY, name="Основная команда")
        self.db.add(row)
        self.db.flush()
        return row

    def get_by_chat_id(self, chat_id: int) -> Team | None:
        return self.db.scalar(select(Team).where(Team.telegram_chat_id == int(chat_id)))

    def get_by_invite(self, code: str) -> Team | None:
        return self.db.scalar(select(Team).where(func.upper(Team.invite_code) == code.strip().upper()))

    def list_active(self, now: datetime) -> list[Team]:
        """Основная команда и песочницы, срок которых ещё не вышел."""
        return list(
            self.db.scalars(
                select(Team).where((Team.kind == TeamKind.PRIMARY) | (Team.expires_at > now))
            )
        )

    def expired_sandboxes(self, now: datetime) -> list[Team]:
        return list(
            self.db.scalars(
                select(Team).where(Team.kind == TeamKind.SANDBOX, Team.expires_at <= now)
            )
        )

    def count_sandboxes_created_since(self, since: datetime) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(Team)
                .where(Team.kind == TeamKind.SANDBOX, Team.created_at >= since)
            )
            or 0
        )

    def add(self, team: Team) -> Team:
        self.db.add(team)
        self.db.flush()
        return team
