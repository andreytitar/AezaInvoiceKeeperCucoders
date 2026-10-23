"""Закоммиченный openapi/openapi.yml совпадает с реально генерируемой схемой (make openapi)."""

import os
from pathlib import Path

from app.openapi_dump import DEFAULT_PATH, render


def test_openapi_yml_is_up_to_date():
    path = Path(os.environ.get("OPENAPI_PATH", DEFAULT_PATH))
    assert path.exists(), "Нет openapi/openapi.yml — выполните make openapi"
    assert path.read_text(encoding="utf-8") == render(), "openapi.yml устарел — выполните make openapi"


def test_all_paths_have_api_v1_prefix():
    import yaml

    schema = yaml.safe_load(render())
    assert all(p.startswith("/api/v1/") for p in schema["paths"])
    required = {
        "/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/auth/logout",
        "/api/v1/recurring-payments", "/api/v1/recurring-payments/{payment_id}",
        "/api/v1/payment-occurrences", "/api/v1/payment-occurrences/{occurrence_id}",
        "/api/v1/payments/summary", "/api/v1/users", "/api/v1/users/{user_id}",
    }
    assert required <= set(schema["paths"])
