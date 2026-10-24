"""Матрица «эндпоинт → роль» (раздел 8.8): 401 для анонима, 403 для user на админских действиях.

Для admin проверяется только, что доступ не запрещён (не 401/403)."""

import uuid

import pytest

RID = str(uuid.uuid4())

# (method, path, body, user_allowed)
MATRIX = [
    ("GET", "/api/v1/auth/me", None, True),
    ("POST", "/api/v1/auth/logout", None, True),
    ("GET", "/api/v1/recurring-payments", None, True),
    ("POST", "/api/v1/recurring-payments", {"title": "T", "amount": "1.00", "currency": "RUB", "first_due_date": "2026-11-01"}, False),
    ("DELETE", f"/api/v1/recurring-payments/{RID}", None, False),
    ("PATCH", f"/api/v1/recurring-payments/{RID}", {"amount": "60000"}, False),
    ("GET", "/api/v1/payment-occurrences", None, True),
    ("GET", f"/api/v1/payment-occurrences/{RID}", None, True),
    ("PATCH", f"/api/v1/payment-occurrences/{RID}", {"status": "paid"}, True),
    ("GET", "/api/v1/payments/summary", None, True),
    ("GET", "/api/v1/payments/summary?as_of=2026-10-01", None, True),
    ("GET", "/api/v1/payments/calendar?from=2026-10-01&to=2026-10-31", None, True),
    ("GET", f"/api/v1/payment-occurrences/{RID}/receipt", None, True),
    ("PUT", f"/api/v1/payment-occurrences/{RID}/receipt", None, True),
    ("DELETE", f"/api/v1/payment-occurrences/{RID}/receipt", None, True),
    ("GET", f"/api/v1/payment-occurrences/{RID}/receipt/file", None, True),
    ("GET", "/api/v1/budgets", None, True),
    ("GET", "/api/v1/budgets/report?year=2026&month=10", None, True),
    ("PUT", "/api/v1/budgets", {"period_type": "month", "year": 2026, "month": 10, "currency": "RUB", "planned_amount": "100.00"}, False),
    ("DELETE", f"/api/v1/budgets/{RID}", None, False),
    ("GET", "/api/v1/webhooks", None, False),
    ("POST", "/api/v1/webhooks", {"url": "http://10.0.0.1/x", "events": ["payment.paid"]}, False),
    ("PATCH", f"/api/v1/webhooks/{RID}", {"is_active": False}, False),
    ("DELETE", f"/api/v1/webhooks/{RID}", None, False),
    ("GET", f"/api/v1/webhooks/{RID}/deliveries", None, False),
    ("POST", f"/api/v1/webhooks/{RID}/test", None, False),
    ("POST", "/api/v1/admin/run-checks", None, False),
    ("GET", "/api/v1/users", None, False),
    ("GET", "/api/v1/audit-logs", None, False),
    ("POST", "/api/v1/users", {"login": "newbie", "password": "secret1"}, False),
    ("PATCH", f"/api/v1/users/{RID}", {"email": "a@b.cd"}, False),
    ("DELETE", f"/api/v1/users/{RID}", None, False),
]


def _call(client, method, path, body):
    return client.request(method, path, json=body)


@pytest.mark.parametrize("method,path,body,user_allowed", MATRIX)
def test_anonymous_gets_401(anon, method, path, body, user_allowed):
    r = _call(anon, method, path, body)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path,body,user_allowed", MATRIX)
def test_user_role(user, method, path, body, user_allowed):
    r = _call(user, method, path, body)
    if user_allowed:
        assert r.status_code not in (401, 403), r.text
    else:
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("method,path,body,user_allowed", MATRIX)
def test_admin_role(admin, method, path, body, user_allowed):
    r = _call(admin, method, path, body)
    assert r.status_code not in (401, 403), r.text


def test_login_open_for_everyone(anon):
    assert anon.post("/api/v1/auth/login", json={"login": "x", "password": "y"}).status_code == 401
