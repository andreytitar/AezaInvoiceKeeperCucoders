from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import bootstrap
from app.main import create_app
from app.services.users import UserService
from tests.conftest import ADMIN_LOGIN, ADMIN_PASSWORD

USER_PASSWORD = "user-pass-123"


@pytest.fixture
def app(container):
    bootstrap(container)
    return create_app(container)


@pytest.fixture
def anon(app):
    return TestClient(app)


def login_client(app, login: str, password: str) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def admin(app):
    return login_client(app, ADMIN_LOGIN, ADMIN_PASSWORD)


@pytest.fixture
def regular_user(container):
    with container.session_factory() as db:
        return UserService(db, container.clock, container.settings).create(login="ivan", password=USER_PASSWORD)


@pytest.fixture
def user(app, regular_user):
    return login_client(app, "ivan", USER_PASSWORD)
