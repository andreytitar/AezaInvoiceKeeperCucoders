from tests.conftest import ADMIN_LOGIN
from tests.integration.conftest import USER_PASSWORD, login_client


def _system_admin_id(admin):
    return admin.get("/api/v1/auth/me").json()["id"]


def test_create_list_update_delete_user(admin):
    r = admin.post("/api/v1/users", json={"login": "petr", "password": "secret1", "email": "p@example.com"})
    assert r.status_code == 201
    uid = r.json()["id"]
    assert r.json()["role"] == "user"
    logins = [u["login"] for u in admin.get("/api/v1/users").json()]
    assert logins == ["petr"]
    r = admin.patch(f"/api/v1/users/{uid}", json={"telegram_user_id": 42})
    assert r.status_code == 200 and r.json()["telegram_user_id"] == 42
    assert admin.delete(f"/api/v1/users/{uid}").status_code == 204
    assert admin.get("/api/v1/users").json() == []
    assert admin.delete(f"/api/v1/users/{uid}").status_code == 404


def test_system_admin_hidden_from_list(admin, regular_user):
    assert ADMIN_LOGIN not in [u["login"] for u in admin.get("/api/v1/users").json()]


def test_system_admin_cannot_be_modified_or_deleted(admin):
    aid = _system_admin_id(admin)
    assert admin.patch(f"/api/v1/users/{aid}", json={"password": "hacked1"}).status_code == 403
    assert admin.delete(f"/api/v1/users/{aid}").status_code == 403


def test_cannot_create_user_with_admin_login(admin):
    r = admin.post("/api/v1/users", json={"login": ADMIN_LOGIN, "password": "secret1"})
    assert r.status_code == 409
    r = admin.post("/api/v1/users", json={"login": ADMIN_LOGIN.upper(), "password": "secret1"})
    assert r.status_code == 409


def test_duplicate_login_409(admin, regular_user):
    assert admin.post("/api/v1/users", json={"login": "ivan", "password": "secret1"}).status_code == 409


def test_role_field_is_rejected(admin):
    r = admin.post("/api/v1/users", json={"login": "boss", "password": "secret1", "role": "admin"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_password_change_revokes_sessions(app, admin, regular_user):
    user = login_client(app, "ivan", USER_PASSWORD)
    assert user.get("/api/v1/auth/me").status_code == 200
    admin.patch(f"/api/v1/users/{regular_user.id}", json={"password": "another1"})
    assert user.get("/api/v1/auth/me").status_code == 401
    login_client(app, "ivan", "another1")


def test_delete_revokes_sessions(app, admin, regular_user):
    user = login_client(app, "ivan", USER_PASSWORD)
    admin.delete(f"/api/v1/users/{regular_user.id}")
    assert user.get("/api/v1/auth/me").status_code == 401


def test_deleted_login_can_be_reused(admin, regular_user):
    admin.delete(f"/api/v1/users/{regular_user.id}")
    assert admin.post("/api/v1/users", json={"login": "ivan", "password": "secret1"}).status_code == 201


def test_telegram_id_unique(admin):
    admin.post("/api/v1/users", json={"login": "aaa1", "password": "secret1", "telegram_user_id": 7})
    r = admin.post("/api/v1/users", json={"login": "aaa2", "password": "secret1", "telegram_user_id": 7})
    assert r.status_code == 409


def test_validation_422(admin):
    assert admin.post("/api/v1/users", json={"login": "a", "password": "1"}).status_code == 422
