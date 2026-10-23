from app.seed import next_day_31, run_seed
from tests.integration.conftest import login_client


def test_seed_is_idempotent_and_covers_demo_cases(container, app, admin, fake_channel):
    assert run_seed(container) is True
    assert run_seed(container) is False
    assert run_seed(container, force=True) is True  # повтор не дублирует
    payments = admin.get("/api/v1/recurring-payments").json()
    assert sorted((p["title"], p["amount"], p["currency"]) for p in payments) == [
        ("Аренда офиса", "55000.00", "RUB"),
        ("Облачное хранилище", "12.50", "USD"),
        ("Подписка JetBrains", "9.99", "EUR"),
        ("Сервер Aeza", "25.00", "USD"),
    ]
    assert any(p["anchor_day"] == 31 for p in payments)
    occ = admin.get("/api/v1/payment-occurrences", params={"page_size": 200}).json()["items"]
    paid = [o for o in occ if o["status"] == "paid"]
    assert any(not o["is_overdue"] for o in paid)  # оплачено в срок
    assert any(o["is_overdue"] for o in paid)  # оплачено с опозданием
    assert any(o["status"] == "unpaid" and o["is_overdue"] for o in occ)  # просрочено
    assert any(o["status"] == "unpaid" and o["days_until_due"] == 2 for o in occ)
    users = [u["login"] for u in admin.get("/api/v1/users").json()]
    assert users == ["ivan", "maria"]
    login_client(app, "maria", container.settings.seed_user_password)


def test_next_day_31():
    from datetime import date

    assert next_day_31(date(2026, 10, 24)) == date(2026, 10, 31)
    assert next_day_31(date(2026, 11, 2)) == date(2026, 12, 31)
