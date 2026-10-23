"""Общие фикстуры: тестовая БД PostgreSQL (не SQLite — нужны SKIP LOCKED и ограничения),
FixedClock, контейнер приложения и клиенты для разных ролей."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.container import Container
from app.domain.clock import FixedClock
from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.rate_limit import LoginRateLimiter
from tests.fakes import FakeChannel

BACKEND = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://invoice:invoice@localhost:55432/invoice_keeper_test"
)
TODAY = date(2026, 10, 24)
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin-pass-123"


def _ensure_database(url: str) -> None:
    u = make_url(url)
    server = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": u.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{u.database}"'))
    server.dispose()


@pytest.fixture(scope="session")
def engine():
    _ensure_database(TEST_DATABASE_URL)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def clean_db(engine):
    with engine.begin() as conn:
        tables = conn.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")
        ).all()
        if tables:
            conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def clock():
    return FixedClock(TODAY)


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        secret_key="test-secret-key-0123456789",
        admin_login=ADMIN_LOGIN,
        admin_password=ADMIN_PASSWORD,
        static_dir="/nonexistent",
        telegram_bot_token=None,
        telegram_chat_id="-100500",
        seed_user_password="user-pass-123",
        seed_on_start=False,
        log_level="WARNING",
        session_ttl_hours=24 * 365 * 3,  # тесты двигают часы на месяцы вперёд
    )


@pytest.fixture
def fake_channel():
    return FakeChannel()


@pytest.fixture
def container(engine, clean_db, clock, settings, fake_channel):
    return Container(
        settings=settings,
        clock=clock,
        session_factory=sessionmaker(bind=engine, expire_on_commit=False, autoflush=False),
        rate_limiter=LoginRateLimiter(settings.login_rate_limit_attempts, settings.login_rate_limit_window_seconds),
        channels=ChannelRegistry([fake_channel]),
    )


@pytest.fixture
def db(container):
    s = container.session_factory()
    yield s
    s.rollback()
    s.close()
