from datetime import date

from sqlalchemy import update

from app.models import RecurringPayment
from app.services.occurrences import OccurrenceGenerator
from tests.integration.helpers import create_payment, occurrences, occurrences_of


def test_create_payment_materializes_first_and_next(admin):
    p = create_payment(admin, first_due_date="2026-11-05")
    assert p["anchor_day"] == 5 and p["recurrence"] == "monthly" and p["amount"] == "55000.00"
    assert p["next_due_date"] == "2026-11-05"
    occ = occurrences_of(admin, p["id"])
    assert [o["due_date"] for o in occ] == ["2026-11-05", "2026-12-05"]
    assert all(o["status"] == "unpaid" and o["paid_date"] is None for o in occ)
    o = occ[0]
    assert set(o) >= {
        "id", "recurring_payment_id", "title", "amount", "currency", "due_date", "status",
        "paid_date", "is_overdue", "overdue_days", "recurring_payment_deleted",
    }
    assert o["amount"] == "55000.00" and isinstance(o["amount"], str)


def test_anchor_31_end_of_month(admin, clock):
    p = create_payment(admin, first_due_date="2026-10-31")
    assert [o["due_date"] for o in occurrences_of(admin, p["id"])] == ["2026-10-31", "2026-11-30"]


def test_past_first_due_creates_history_and_overdue(admin):
    p = create_payment(admin, first_due_date="2026-09-20")
    occ = occurrences_of(admin, p["id"])
    assert [o["due_date"] for o in occ] == ["2026-09-20", "2026-10-20", "2026-11-20"]
    assert [o["overdue_days"] for o in occ] == [34, 4, 0]


def test_amount_and_currency_validation(admin):
    base = {"title": "X", "currency": "USD", "first_due_date": "2026-11-01"}
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": "1.005"}).status_code == 422
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": "0"}).status_code == 422
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": "-5"}).status_code == 422
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": "5", "currency": "GBP"}).status_code == 422
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": "5", "first_due_date": "2020-01-01"}).status_code == 422
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": "9.99", "foo": 1}).status_code == 422
    assert admin.post("/api/v1/recurring-payments", json={**base, "amount": 9.99}).json()["amount"] == "9.99"


def test_user_cannot_create_or_delete(admin, user):
    p = create_payment(admin)
    r = user.post("/api/v1/recurring-payments", json={"title": "X", "amount": "1", "currency": "RUB", "first_due_date": "2026-11-01"})
    assert r.status_code == 403
    assert user.delete(f"/api/v1/recurring-payments/{p['id']}").status_code == 403
    assert len(user.get("/api/v1/recurring-payments").json()) == 1


def test_mark_paid_defaults_to_today_and_unmark_clears_date(admin, user):
    p = create_payment(admin)
    oid = occurrences_of(user, p["id"])[0]["id"]
    r = user.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "paid"})
    assert r.status_code == 200
    assert r.json()["status"] == "paid" and r.json()["paid_date"] == "2026-10-24"
    r = user.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "unpaid"})
    assert r.json()["status"] == "unpaid" and r.json()["paid_date"] is None


def test_patch_validation(admin, user):
    p = create_payment(admin)
    oid = occurrences_of(user, p["id"])[0]["id"]
    url = f"/api/v1/payment-occurrences/{oid}"
    assert user.patch(url, json={"status": "paid", "paid_date": "2026-10-25"}).status_code == 422  # будущее
    assert user.patch(url, json={"status": "unpaid", "paid_date": "2026-10-20"}).status_code == 422
    assert user.patch(url, json={"paid_date": "2026-10-20"}).status_code == 422  # без статуса
    assert user.patch(url, json={"status": "paid", "due_date": "2026-12-01"}).status_code == 422  # extra=forbid
    assert user.patch(url, json={"status": "paid", "amount": "1"}).status_code == 422
    assert user.patch(url, json={"status": "maybe"}).status_code == 422
    assert user.patch("/api/v1/payment-occurrences/00000000-0000-0000-0000-000000000000", json={"status": "paid"}).status_code == 404


def test_correcting_paid_date_removes_wrong_overdue_and_keeps_due(admin, user):
    p = create_payment(admin, first_due_date="2026-10-10")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    url = f"/api/v1/payment-occurrences/{oid}"
    wrong = user.patch(url, json={"status": "paid", "paid_date": "2026-10-15"}).json()
    assert wrong["is_overdue"] is True and wrong["overdue_days"] == 5
    fixed = user.patch(url, json={"status": "paid", "paid_date": "2026-10-09"}).json()
    assert fixed["is_overdue"] is False and fixed["overdue_days"] == 0
    assert fixed["due_date"] == "2026-10-10"


def test_paid_on_due_date_is_on_time(admin, user):
    p = create_payment(admin, first_due_date="2026-10-24")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    r = user.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "paid", "paid_date": "2026-10-24"}).json()
    assert r["is_overdue"] is False


def test_repeat_mark_is_idempotent(admin, user):
    p = create_payment(admin, first_due_date="2026-10-10")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    url = f"/api/v1/payment-occurrences/{oid}"
    first = user.patch(url, json={"status": "paid", "paid_date": "2026-10-09"}).json()
    again = user.patch(url, json={"status": "paid"}).json()
    assert again["paid_date"] == first["paid_date"] == "2026-10-09"


def test_next_period_has_separate_status_and_history_kept(admin, user):
    p = create_payment(admin, first_due_date="2026-10-25")
    first, second = occurrences_of(admin, p["id"])
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "paid"})
    occ = occurrences_of(admin, p["id"])
    assert [o["status"] for o in occ] == ["paid", "unpaid", "unpaid"]
    assert occ[1]["id"] == second["id"]
    assert [o["due_date"] for o in occ] == ["2026-10-25", "2026-11-25", "2026-12-25"]


def test_new_periods_do_not_erase_past_and_overdue_does_not_block(admin, container, clock):
    p = create_payment(admin, first_due_date="2026-10-25")
    clock.set_today(date(2027, 1, 3))
    with container.session_factory() as db:
        OccurrenceGenerator(db, clock).ensure_all()
        OccurrenceGenerator(db, clock).ensure_all()  # идемпотентно
    occ = occurrences_of(admin, p["id"])
    assert [o["due_date"] for o in occ] == ["2026-10-25", "2026-11-25", "2026-12-25", "2027-01-25"]
    assert [o["is_overdue"] for o in occ] == [True, True, True, False]


def test_snapshot_not_changed_when_template_changes(admin, container, clock):
    p = create_payment(admin, title="Сервер", amount="25.00", currency="USD", first_due_date="2026-10-25")
    with container.session_factory() as db:
        db.execute(update(RecurringPayment).where(RecurringPayment.id == p["id"]).values(title="Сервер v2", amount="30.00"))
        db.commit()
    clock.set_today(date(2026, 11, 26))
    with container.session_factory() as db:
        OccurrenceGenerator(db, clock).ensure_all()
    occ = occurrences_of(admin, p["id"])
    assert [(o["title"], o["amount"]) for o in occ[:2]] == [("Сервер", "25.00"), ("Сервер", "25.00")]
    assert (occ[-1]["title"], occ[-1]["amount"]) == ("Сервер v2", "30.00")


def test_delete_keeps_history_and_removes_future_unpaid(admin, user, container, clock):
    p = create_payment(admin, first_due_date="2026-09-20")  # 20.09 и 20.10 в прошлом, 20.11 в будущем
    occ = occurrences_of(admin, p["id"])
    admin.patch(f"/api/v1/payment-occurrences/{occ[0]['id']}", json={"status": "paid", "paid_date": "2026-09-19"})
    assert admin.delete(f"/api/v1/recurring-payments/{p['id']}").status_code == 204
    assert admin.delete(f"/api/v1/recurring-payments/{p['id']}").status_code == 404
    left = occurrences_of(user, p["id"])
    assert [o["due_date"] for o in left] == ["2026-09-20", "2026-10-20"]
    assert all(o["recurring_payment_deleted"] for o in left)
    assert left[1]["is_overdue"] is True  # просроченный неоплаченный остаётся в истории
    # новые периоды больше не создаются
    clock.set_today(date(2027, 3, 1))
    with container.session_factory() as db:
        OccurrenceGenerator(db, clock).ensure_all()
    assert len(occurrences_of(user, p["id"])) == 2
    assert user.get("/api/v1/recurring-payments").json() == []
    listed = user.get("/api/v1/recurring-payments", params={"include_deleted": True}).json()
    assert listed[0]["is_deleted"] is True


def test_filters_pagination_sort(admin, user):
    create_payment(admin, title="Аренда", amount="55000", currency="RUB", first_due_date="2026-10-20")
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-11-10")
    assert len(occurrences(user, currency="USD")) == 2
    overdue = occurrences(user, overdue=True)
    assert [o["title"] for o in overdue] == ["Аренда"]
    assert len(occurrences(user, status="paid")) == 0
    assert [o["due_date"] for o in occurrences(user, **{"from": "2026-11-01", "to": "2026-11-30"})] == [
        "2026-11-10", "2026-11-20", "2026-11-26",
    ]
    r = user.get("/api/v1/payment-occurrences", params={"page": 2, "page_size": 2}).json()
    assert r["total"] == 6 and len(r["items"]) == 2 and r["page"] == 2
    amounts = [o["amount"] for o in occurrences(user, sort="-amount")]
    assert amounts[0] == "55000.00"
    assert [o["title"] for o in occurrences(user, q="серв")] == ["Сервер", "Сервер"]
    assert user.get("/api/v1/payment-occurrences", params={"sort": "drop table"}).status_code == 422


def test_summary_per_currency_without_mixing(admin, user):
    a = create_payment(admin, title="Аренда", amount="55000", currency="RUB", first_due_date="2026-10-20")
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-11-10")
    first = occurrences_of(admin, a["id"])[0]
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "paid", "paid_date": "2026-10-21"})
    s = {c["currency"]: c for c in user.get("/api/v1/payments/summary").json()["currencies"]}
    assert set(s) == {"RUB", "USD", "EUR"}
    # оплата первого периода материализует ещё один: 20.10 (оплачен), 20.11, 20.12
    assert s["RUB"]["total"] == {"amount": "165000.00", "count": 3}
    assert s["RUB"]["paid"] == {"amount": "55000.00", "count": 1}
    assert s["RUB"]["unpaid"] == {"amount": "110000.00", "count": 2}
    assert s["RUB"]["overdue"] == {"amount": "0.00", "count": 0}
    assert s["USD"]["total"] == {"amount": "50.00", "count": 2}
    assert s["EUR"]["unpaid"] == {"amount": "19.98", "count": 2}


def test_summary_counts_overdue(admin, user):
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-19")
    s = {c["currency"]: c for c in user.get("/api/v1/payments/summary").json()["currencies"]}
    assert s["EUR"]["overdue"] == {"amount": "9.99", "count": 1}
