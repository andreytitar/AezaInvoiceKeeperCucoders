"""Проверка подписи initData Telegram Mini App."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import pytest

from app.domain.errors import Unauthorized
from app.services.telegram_login import data_check_string, verify_webapp_init_data


def _sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check_string(fields).encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def test_verify_webapp_init_data_accepts_valid_signature():
    token = "123456:ABC-DEF"
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    user = json.dumps({"id": 424242, "first_name": "Test"}, separators=(",", ":"))
    fields = {"auth_date": str(int(now.timestamp())), "query_id": "AAE", "user": user}
    init_data = _sign_init_data(fields, token)
    assert verify_webapp_init_data(init_data, token, now) == 424242


def test_verify_webapp_init_data_rejects_tampered_user():
    token = "123456:ABC-DEF"
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    user = json.dumps({"id": 1, "first_name": "A"}, separators=(",", ":"))
    fields = {"auth_date": str(int(now.timestamp())), "user": user}
    init_data = _sign_init_data(fields, token)
    bad = init_data.replace("first_name", "first_namе")  # кириллическая «е»
    with pytest.raises(Unauthorized):
        verify_webapp_init_data(bad, token, now)


def test_resolve_mini_app_url_requires_https():
    from app.config import Settings
    from app.services.telegram_profile import resolve_mini_app_url

    assert resolve_mini_app_url(Settings.model_construct(secret_key="x" * 16, public_base_url="http://localhost:8000")) is None
    assert (
        resolve_mini_app_url(
            Settings.model_construct(
                secret_key="x" * 16,
                public_base_url="https://panel.example.com/app",
            )
        )
        == "https://panel.example.com/app/"
    )
