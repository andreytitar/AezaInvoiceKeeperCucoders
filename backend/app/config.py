"""Настройки приложения. Все параметры берутся только из окружения / .env."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- База и безопасность ---
    database_url: str = "postgresql+psycopg://invoice:invoice@db:5432/invoice_keeper"
    secret_key: str = Field(min_length=16)
    admin_login: str = Field(default="admin", min_length=3, max_length=64)
    admin_password: str = Field(min_length=6)
    cookie_secure: bool = False
    session_ttl_hours: int = 24 * 7
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    # --- Время ---
    app_timezone: str = "Europe/Moscow"
    app_fake_today: date | None = None  # демо-инструмент, по умолчанию выключен

    # --- Напоминания ---
    reminder_days_before: int = Field(default=3, ge=3, le=60)
    worker_interval_seconds: int = Field(default=60, ge=1)
    digest_weekday: int = Field(default=0, ge=-1, le=6)  # 0 — понедельник, -1 — сводка выключена
    digest_hour: int = Field(default=9, ge=0, le=23)
    overdue_remind_every_days: int = Field(default=3, ge=0, le=60)  # 0 — повторы о просрочке выключены
    overdue_remind_max: int = Field(default=5, ge=0, le=50)
    delivery_max_attempts: int = 5
    delivery_stale_seconds: int = 300

    # --- Telegram ---
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_api_base: str = "https://api.telegram.org"
    telegram_polling_enabled: bool = True
    # Публичный адрес панели: одноразовые ссылки из бота ведут сюда
    public_base_url: str = "http://localhost:8000"

    # --- Email (SMTP) ---
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Invoice Keeper <invoice-keeper@localhost>"
    smtp_security: str = Field(default="starttls", pattern="^(starttls|ssl|none)$")
    smtp_timeout_seconds: float = 15.0
    email_recipients: str = ""  # общий список через запятую
    email_to_users: bool = True  # плюс email из профилей пользователей

    # --- Webhook ---
    webhook_allow_private: bool = False  # разрешить loopback/private/link-local (локальное демо)
    webhook_timeout_seconds: float = 10.0

    # --- Чат-вебхук (Slack / Discord / Mattermost incoming webhook) ---
    chat_webhook_url: str | None = None
    chat_webhook_format: str = Field(default="auto", pattern="^(auto|slack|discord|mattermost)$")

    # --- Сид ---
    seed_on_start: bool = True
    seed_user_password: str = Field(default="user12345", min_length=6)

    # --- Чеки ---
    uploads_dir: str = "/app/uploads"
    receipt_max_bytes: int = 5 * 1024 * 1024

    # --- Прочее ---
    log_level: str = "INFO"
    static_dir: str = "/app/static"

    @field_validator("app_timezone")
    @classmethod
    def _tz_exists(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - понятная ошибка при старте
            raise ValueError(f"Неизвестный часовой пояс APP_TIMEZONE={v!r}") from exc
        return v

    @field_validator(
        "telegram_bot_token", "telegram_chat_id", "app_fake_today", "smtp_host", "smtp_user", "smtp_password",
        "chat_webhook_url",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def email_static_recipients(self) -> list[str]:
        return [e.strip() for e in self.email_recipients.split(",") if e.strip()]

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            name = str(err["loc"][0]).upper() if err["loc"] else "?"
            problems.append(f"  {name}: {'не задана' if err['type'] == 'missing' else err['msg']}")
        raise SystemExit("Ошибка конфигурации (.env):\n" + "\n".join(problems)) from None
