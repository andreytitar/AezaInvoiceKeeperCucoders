from tests.integration.helpers import create_payment, occurrences_of


def cur(summary, code):
    return next(c for c in summary["currencies"] if c["currency"] == code)


def test_summary_as_of_date(admin, user):
    p = create_payment(admin, title="Аренда", amount="1000", currency="RUB", first_due_date="2026-09-10")
    occ = occurrences_of(admin, p["id"])  # 10.09, 10.10, 10.11
    user.patch(f"/api/v1/payment-occurrences/{occ[0]['id']}", json={"status": "paid", "paid_date": "2026-09-15"})
    # на 12.09: 10.09 ещё не оплачен (оплата 15.09) -> просрочен; 10.10 и 10.11 предстоят
    s = cur(user.get("/api/v1/payments/summary", params={"as_of": "2026-09-12"}).json(), "RUB")
    assert s["paid"]["count"] == 0 and s["overdue"] == {"amount": "1000.00", "count": 1}
    assert s["upcoming"]["count"] == 2
    # на 20.09: 10.09 оплачен
    s = cur(user.get("/api/v1/payments/summary", params={"as_of": "2026-09-20"}).json(), "RUB")
    assert s["paid"] == {"amount": "1000.00", "count": 1} and s["overdue"]["count"] == 0
    # сегодня (24.10): 10.10 просрочен
    s = user.get("/api/v1/payments/summary").json()
    assert s["as_of"] == "2026-10-24"
    r = cur(s, "RUB")
    assert r["overdue"]["count"] == 1 and r["upcoming"]["count"] == 1 and r["paid"]["count"] == 1
    assert cur(s, "USD")["total"]["count"] == 0


def test_calendar_groups_by_day_with_currency_totals(admin, user):
    a = create_payment(admin, title="Аренда", amount="55000", currency="RUB", first_due_date="2026-10-20")
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-20")
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-28")
    occ = occurrences_of(admin, a["id"])[0]
    user.patch(f"/api/v1/payment-occurrences/{occ['id']}", json={"status": "paid", "paid_date": "2026-10-19"})
    r = user.get("/api/v1/payments/calendar", params={"from": "2026-10-01", "to": "2026-10-31"})
    assert r.status_code == 200
    body = r.json()
    assert body["from"] == "2026-10-01" and body["today"] == "2026-10-24"
    days = {d["date"]: d for d in body["days"]}
    assert set(days) == {"2026-10-20", "2026-10-28"}
    d20 = days["2026-10-20"]
    assert [o["title"] for o in d20["occurrences"]] == ["Аренда", "Сервер"]
    assert [o["status"] for o in d20["occurrences"]] == ["paid", "unpaid"]
    totals = {t["currency"]: t for t in d20["totals"]}
    assert set(totals) == {"RUB", "USD"}
    assert totals["RUB"]["paid"]["amount"] == "55000.00" and totals["USD"]["overdue"]["amount"] == "25.00"


def test_calendar_validation(user):
    assert user.get("/api/v1/payments/calendar", params={"from": "2026-10-31", "to": "2026-10-01"}).status_code == 422
    assert user.get("/api/v1/payments/calendar", params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 422
    assert user.get("/api/v1/payments/calendar").status_code == 422
