from fastapi.testclient import TestClient

from tests.conftest import ADMIN_LOGIN, ADMIN_PASSWORD
from tests.integration.conftest import USER_PASSWORD, login_client


def test_login_sets_httponly_cookie_and_returns_token(anon):
    r = anon.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin" and body["user"]["is_system"] is True
    assert body["access_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_wrong_password_401_with_error_format(anon):
    r = anon.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"
    assert set(r.json()["error"]) == {"code", "message", "details"}


def test_me_requires_auth(anon):
    r = anon.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_bearer_token_works(app, anon):
    token = anon.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD}).json()[
        "access_token"
    ]
    fresh = TestClient(app)
    assert fresh.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_oauth2_token_endpoint_for_swagger(anon):
    r = anon.post("/api/v1/auth/token", data={"username": ADMIN_LOGIN, "password": ADMIN_PASSWORD})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_logout_invalidates_session_on_server(app, anon):
    token = anon.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD}).json()[
        "access_token"
    ]
    h = {"Authorization": f"Bearer {token}"}
    c = TestClient(app)
    assert c.post("/api/v1/auth/logout", headers=h).status_code == 204
    assert c.get("/api/v1/auth/me", headers=h).status_code == 401


def test_login_rate_limit(anon):
    for _ in range(5):
        assert anon.post("/api/v1/auth/login", json={"login": "x-user", "password": "bad"}).status_code == 401
    r = anon.post("/api/v1/auth/login", json={"login": "x-user", "password": "bad"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "too_many_requests"


def test_csrf_foreign_origin_rejected_for_cookie_session(admin):
    r = admin.post("/api/v1/users", json={"login": "evil", "password": "123456"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = admin.post("/api/v1/users", json={"login": "good", "password": "123456"}, headers={"Origin": "http://testserver"})
    assert r.status_code == 201


def test_admin_password_change_in_env_applies_after_restart(container, app):
    from app.bootstrap import bootstrap

    login_client(app, ADMIN_LOGIN, ADMIN_PASSWORD)
    container.settings.admin_password = "new-admin-pass"
    bootstrap(container)  # «рестарт»
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD}).status_code == 401
    assert c.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": "new-admin-pass"}).status_code == 200


def test_bootstrap_is_idempotent(container, app):
    from app.bootstrap import bootstrap

    bootstrap(container)
    bootstrap(container)
    admin = login_client(app, ADMIN_LOGIN, ADMIN_PASSWORD)
    assert admin.get("/api/v1/auth/me").json()["login"] == ADMIN_LOGIN


def test_user_login(user):
    assert user.get("/api/v1/auth/me").json()["role"] == "user"


def test_regular_user_password(app, regular_user):
    login_client(app, "ivan", USER_PASSWORD)
