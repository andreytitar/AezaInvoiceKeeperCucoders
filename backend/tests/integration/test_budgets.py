from tests.integration.helpers import create_payment, occurrences_of


def line(report, cur):
    return next(x for x in report["lines"] if x["currency"] == cur)


def test_budget_upsert_and_report(admin, user):
    r = admin.put("/api/v1/budgets", json={"period_type": "month", "year": 2026, "month": 11, "currency": "RUB", "planned_amount": "100000"})
    assert r.status_code == 201
    r = admin.put("/api/v1/budgets", json={"period_type": "month", "year": 2026, "month": 11, "currency": "RUB", "planned_amount": "50000"})
    assert r.status_code == 200 and r.json()["planned_amount"] == "50000.00"
    admin.put("/api/v1/budgets", json={"period_type": "month", "year": 2026, "month": 11, "currency": "USD", "planned_amount": "100"})
    a = create_payment(admin, title="Аренда", amount="55000", currency="RUB", first_due_date="2026-11-05")
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-11-10")
    oid = occurrences_of(admin, a["id"])[0]["id"]
    admin.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "paid"})
    rep = user.get("/api/v1/budgets/report", params={"year": 2026, "month": 11}).json()
    assert rep["date_from"] == "2026-11-01" and rep["date_to"] == "2026-11-30"
    rub = line(rep, "RUB")
    assert rub["budget"] == "50000.00" and rub["scheduled"] == "55000.00" and rub["paid"] == "55000.00"
    assert rub["is_over"] is True and rub["overrun"] == "5000.00" and rub["remaining"] == "0.00"
    usd = line(rep, "USD")
    assert usd["remaining"] == "75.00" and usd["is_over"] is False and usd["usage_percent"] == 25.0
    eur = line(rep, "EUR")
    assert eur["budget"] is None and eur["scheduled"] == "0.00"
    assert len(user.get("/api/v1/budgets", params={"year": 2026}).json()) == 2


def test_year_budget(admin, user):
    admin.put("/api/v1/budgets", json={"period_type": "year", "year": 2026, "currency": "EUR", "planned_amount": "100"})
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-19")
    rep = user.get("/api/v1/budgets/report", params={"period_type": "year", "year": 2026}).json()
    eur = line(rep, "EUR")
    assert eur["scheduled"] == "19.98" and eur["count"] == 2 and eur["remaining"] == "80.02"


def test_budget_validation(admin):
    base = {"period_type": "month", "year": 2026, "currency": "RUB", "planned_amount": "1"}
    assert admin.put("/api/v1/budgets", json=base).status_code == 422  # нет месяца
    assert admin.put("/api/v1/budgets", json={**base, "period_type": "year", "month": 3}).status_code == 422
    assert admin.put("/api/v1/budgets", json={**base, "month": 13}).status_code == 422
    assert admin.put("/api/v1/budgets", json={**base, "month": 1, "planned_amount": "-1"}).status_code == 422
    assert admin.put("/api/v1/budgets", json={**base, "month": 1, "currency": "GBP"}).status_code == 422


def test_user_cannot_change_budgets_and_delete(admin, user):
    b = admin.put("/api/v1/budgets", json={"period_type": "year", "year": 2027, "currency": "USD", "planned_amount": "10"}).json()
    assert user.put("/api/v1/budgets", json={"period_type": "year", "year": 2027, "currency": "USD", "planned_amount": "1"}).status_code == 403
    assert user.delete(f"/api/v1/budgets/{b['id']}").status_code == 403
    assert admin.delete(f"/api/v1/budgets/{b['id']}").status_code == 204
    assert admin.delete(f"/api/v1/budgets/{b['id']}").status_code == 404
    actions = [i["action"] for i in admin.get("/api/v1/audit-logs", params={"action": "budget."}).json()["items"]]
    assert actions == ["budget.delete", "budget.create"]
