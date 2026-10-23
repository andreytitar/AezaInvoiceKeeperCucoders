"""Матрица «эндпоинт → роль» (раздел 8.8): 401 для анонима, 403 для user на админских действиях.

Для admin проверяется только, что доступ не запрещён (не 401/403)."""

import uuid

import pytest

RID = str(uuid.uuid4())

# (method, path, body, user_allowed)
MATRIX = [
    ("GET", "/api/v1/auth/me", None, True),
    ("POST", "/api/v1/auth/logout", None, True),
    ("GET", "/api/v1/users", None, False),
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
