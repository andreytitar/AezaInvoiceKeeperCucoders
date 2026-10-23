from tests.conftest import ADMIN_LOGIN, ADMIN_PASSWORD
from tests.integration.conftest import login_client
from tests.integration.helpers import create_payment, occurrences_of


def audit(admin, **params):
    r = admin.get("/api/v1/audit-logs", params={"page_size": 200, **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_login_success_and_failure_logged(admin, anon):
    anon.post("/api/v1/auth/login", json={"login": "ghost", "password": "wrong"}, headers={"User-Agent": "pytest-ua"})
    items = audit(admin, action="auth.")
    failed = [i for i in items if i["action"] == "auth.login_failed"]
    assert failed and failed[0]["actor_login"] == "ghost" and failed[0]["user_agent"] == "pytest-ua"
    assert failed[0]["ip"]
    assert any(i["action"] == "auth.login" and i["actor_login"] == ADMIN_LOGIN for i in items)


def test_logout_logged(app, admin):
    admin.post("/api/v1/auth/logout")
    other = login_client(app, ADMIN_LOGIN, ADMIN_PASSWORD)
    assert audit(other, action="auth.logout")[0]["actor_login"] == ADMIN_LOGIN



def test_payment_and_occurrence_actions_logged(admin, user):
    p = create_payment(admin, first_due_date="2026-10-20")
    occ = occurrences_of(admin, p["id"])[0]
    url = f"/api/v1/payment-occurrences/{occ['id']}"
    user.patch(url, json={"status": "paid", "paid_date": "2026-10-22"})
    user.patch(url, json={"status": "paid", "paid_date": "2026-10-19"})
    user.patch(url, json={"status": "unpaid"})
    admin.delete(f"/api/v1/recurring-payments/{p['id']}")
    items = audit(admin)
    actions = [i["action"] for i in items]
    for a in ("payment.create", "occurrence.paid", "occurrence.paid_date_changed", "occurrence.unpaid", "payment.delete"):
        assert a in actions, a
    changed = next(i for i in items if i["action"] == "occurrence.paid_date_changed")
    assert changed["actor_login"] == "ivan"
    assert changed["before"]["paid_date"] == "2026-10-22" and changed["after"]["paid_date"] == "2026-10-19"
    assert audit(admin, entity_id=occ["id"])[0]["entity_type"] == "payment_occurrence"


def test_user_management_logged_without_passwords(admin):
    r = admin.post("/api/v1/users", json={"login": "petr", "password": "super-secret-1"})
    uid = r.json()["id"]
    admin.patch(f"/api/v1/users/{uid}", json={"password": "another-secret-2"})
    admin.delete(f"/api/v1/users/{uid}")
    items = audit(admin, action="user.")
    assert [i["action"] for i in items] == ["user.delete", "user.update", "user.create"]
    assert items[1]["after"]["password_changed"] is True
    import json

    dump = json.dumps(items)
    assert "super-secret-1" not in dump and "another-secret-2" not in dump and "password_hash" not in dump


def test_notification_sent_logged(admin):
    create_payment(admin, first_due_date="2026-10-25")
    sent = audit(admin, action="notification.")
    assert sent and sent[0]["action"] == "notification.sent" and sent[0]["actor_login"] == "worker"


def test_filters_and_pagination(admin):
    for i in range(3):
        create_payment(admin, title=f"P{i}", first_due_date="2026-11-10")
    r = admin.get("/api/v1/audit-logs", params={"action": "payment.create", "page_size": 2}).json()
    assert r["total"] == 3 and len(r["items"]) == 2
    assert audit(admin, actor_login="nobody") == []
    assert len(audit(admin, **{"from": "2026-10-24", "to": "2026-10-24", "action": "payment.create"})) == 3
    assert audit(admin, **{"from": "2026-10-25", "action": "payment.create"}) == []
