from __future__ import annotations

from datetime import date


def create_payment(client, title="Аренда", amount="55000.00", currency="RUB", first_due_date: date | str = "2026-11-05", **kw):
    if isinstance(first_due_date, date):
        first_due_date = first_due_date.isoformat()
    r = client.post(
        "/api/v1/recurring-payments",
        json={"title": title, "amount": amount, "currency": currency, "first_due_date": first_due_date, **kw},
    )
    assert r.status_code == 201, r.text
    return r.json()


def occurrences(client, **params):
    r = client.get("/api/v1/payment-occurrences", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def occurrences_of(client, payment_id):
    return occurrences(client, recurring_payment_id=payment_id, sort="due_date")
