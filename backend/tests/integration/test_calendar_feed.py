from tests.integration.helpers import create_payment, occurrences_of


def test_ics_feed(admin, user, anon):
    p = create_payment(admin, title="Аренда, офис; №1", amount="55000", first_due_date="2026-10-20")
    create_payment(admin, title="Домен", amount="12", currency="USD", first_due_date="2026-12-01", recurrence="yearly")
    oid = occurrences_of(admin, p["id"])[0]["id"]
    admin.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "paid", "paid_date": "2026-10-19"})
    feed = user.get("/api/v1/calendar/feed").json()
    assert feed["url"].endswith(".ics") and feed["webcal_url"].startswith("webcal://")
    path = "/" + feed["url"].split("/", 3)[3]
    r = anon.get(path)  # календарные приложения ходят без cookie — доступ по секретной ссылке
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.rstrip().endswith("END:VCALENDAR")
    assert "Оплачено: Аренда\\, офис\; №1" in body  # экранирование RFC 5545
    assert "DTSTART;VALUE=DATE:20261120" in body  # следующий период
    assert "DTSTART;VALUE=DATE:20270920" in body  # прогноз на год вперёд
    assert "DTSTART;VALUE=DATE:20271201" in body  # ежегодный платёж через год
    assert "TRIGGER:-P2DT15H" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    assert body.count("UID:") == len(set(l for l in body.split("\r\n") if l.startswith("UID:")))
    # смена ссылки — старая перестаёт работать
    new = user.post("/api/v1/calendar/feed/rotate").json()
    assert new["url"] != feed["url"] and anon.get(path).status_code == 404
    assert user.get("/api/v1/calendar/feed").json()["url"] == new["url"]


def test_deleted_user_feed_disabled(admin, regular_user, app):
    from tests.integration.conftest import USER_PASSWORD, login_client

    u = login_client(app, "ivan", USER_PASSWORD)
    url = u.get("/api/v1/calendar/feed").json()["url"]
    admin.delete(f"/api/v1/users/{regular_user.id}")
    assert admin.get("/" + url.split("/", 3)[3]).status_code == 404
