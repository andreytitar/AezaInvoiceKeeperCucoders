from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession

from app.models import Session, User


class UserRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))

    def get_by_login(self, login: str) -> User | None:
        return self.db.scalar(
            select(User).where(func.lower(User.login) == login.lower(), User.deleted_at.is_(None))
        )

    def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        return self.db.scalar(
            select(User).where(User.telegram_user_id == telegram_user_id, User.deleted_at.is_(None))
        )

    def list_regular(self, team_id: uuid.UUID | None = None) -> list[User]:
        stmt = select(User).where(User.deleted_at.is_(None), User.is_system.is_(False))
        if team_id is not None:
            stmt = stmt.where(User.team_id == team_id)
        return list(self.db.scalars(stmt.order_by(User.login)))

    def list_system(self) -> list[User]:
        return list(self.db.scalars(select(User).where(User.is_system.is_(True), User.deleted_at.is_(None))))

    def active_emails(self, team_id: uuid.UUID | None = None) -> list[str]:
        stmt = select(User.email).where(User.deleted_at.is_(None), User.email.is_not(None))
        if team_id is not None:
            stmt = stmt.where(User.team_id == team_id)
        return [e for e in self.db.scalars(stmt.order_by(User.login)) if e]

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user


class SessionRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def add(self, s: Session) -> Session:
        self.db.add(s)
        self.db.flush()
        return s

    def get_active_by_hash(self, token_hash: str, now: datetime) -> Session | None:
        return self.db.scalar(
            select(Session).where(
                Session.token_hash == token_hash,
                Session.revoked_at.is_(None),
                Session.expires_at > now,
            )
        )

    def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        self.db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
