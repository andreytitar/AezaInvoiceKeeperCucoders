#!/usr/bin/env python3
"""Проверка критериев приёмки и демо-сценария против запущенного стека.

    python3 scripts/acceptance.py [--base http://localhost:8000] [--admin admin:change-me-admin] [--user ivan:user12345]

Только стандартная библиотека. Создаёт тестовый платёж «Приёмка …» и в конце удаляет его.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

OK, FAIL = "  ok ", "  FAIL"
failures: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"{OK if cond else FAIL} {label}")
    if not cond:
        failures.append(label)


class Client:
    def __init__(self, base: str, token: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def req(self, method: str, path: str, body=None, raw: bool = False):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        if self.token:
            r.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                payload = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            payload, status = e.read(), e.code
        if raw:
            return status, payload
        return status, (json.loads(payload) if payload else None)

    def login(self, login: str, password: str) -> "Client":
        status, body = self.req("POST", "/api/v1/auth/login", {"login": login, "password": password})
        if status != 200:
            sys.exit(f"Не удалось войти как {login}: {status} {body}")
        return Client(self.base, body["access_token"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--admin", default="admin:change-me-admin")
    ap.add_argument("--user", default="ivan:user12345")
    a = ap.parse_args()
    anon = Client(a.base)
    admin = anon.login(*a.admin.split(":", 1))
    user = anon.login(*a.user.split(":", 1))
    today = date.fromisoformat(anon.req("GET", "/api/v1/health")[1]["today"])
    print(f"Стек: {a.base}, сегодня {today}")

    print("\n1. Без авторизации панель и данные недоступны")
    check(anon.req("GET", "/api/v1/payment-occurrences")[0] == 401, "GET /payment-occurrences без токена -> 401")
    check(anon.req("GET", "/api/v1/payments/summary")[0] == 401, "GET /payments/summary без токена -> 401")
    status, html = anon.req("GET", "/", raw=True)
    check(status == 200 and b'id="root"' in html, "SPA отдаётся (редирект на /login делает клиент)")

    print("\n2. Пользователь не выполнит действия администратора через API")
    body = {"title": "x", "amount": "1.00", "currency": "RUB", "first_due_date": today.isoformat()}
    check(user.req("POST", "/api/v1/recurring-payments", body)[0] == 403, "user POST /recurring-payments -> 403")
    any_id = admin.req("GET", "/api/v1/recurring-payments")[1]
    if any_id:
        check(user.req("DELETE", f"/api/v1/recurring-payments/{any_id[0]['id']}")[0] == 403, "user DELETE /recurring-payments -> 403")
    check(user.req("GET", "/api/v1/users")[0] == 403, "user GET /users -> 403")
    check(user.req("POST", "/api/v1/users", {"login": "hacker", "password": "123456"})[0] == 403, "user POST /users -> 403")

    print("\nДемо: админ добавляет платёж со сроком через 2 дня")
    title = f"Приёмка {today.isoformat()}"
    due = today + timedelta(days=2)
    status, p = admin.req(
        "POST", "/api/v1/recurring-payments",
        {"title": title, "amount": "1234.56", "currency": "USD", "first_due_date": due.isoformat()},
    )
    check(status == 201, "POST /recurring-payments -> 201")
    pid = p["id"]
    occ = user.req("GET", f"/api/v1/payment-occurrences?recurring_payment_id={pid}&sort=due_date")[1]["items"]

    print("\n3. Следующий период существует с отдельным статусом")
    check(len(occ) == 2 and occ[0]["due_date"] == due.isoformat(), "созданы ближайший и следующий периоды")
    first, second = occ[0], occ[1]

    print("\n5. Оплата: отметить, отменить, исправить дату")
    url = f"/api/v1/payment-occurrences/{first['id']}"
    r = user.req("PATCH", url, {"status": "paid"})[1]
    check(r["status"] == "paid" and r["paid_date"] == today.isoformat(), "user отметил оплату, дата = сегодня")
    r = user.req("PATCH", url, {"status": "unpaid"})[1]
    check(r["status"] == "unpaid" and r["paid_date"] is None, "отмена оплаты очищает дату")
    check(user.req("PATCH", url, {"status": "paid", "paid_date": (today + timedelta(days=1)).isoformat()})[0] == 422, "дата в будущем -> 422")
    check(user.req("PATCH", url, {"status": "paid", "due_date": today.isoformat()})[0] == 422, "менять срок через PATCH нельзя -> 422")
    overdue_items = user.req("GET", "/api/v1/payment-occurrences?status=unpaid&overdue=true&page_size=200")[1]["items"]
    if overdue_items:
        o = overdue_items[0]
        ourl = f"/api/v1/payment-occurrences/{o['id']}"
        late = user.req("PATCH", ourl, {"status": "paid", "paid_date": today.isoformat()})[1]
        check(late["is_overdue"] and late["overdue_days"] == o["overdue_days"], f"оплата позже срока -> просрочка {late['overdue_days']} дн.")
        fixed = user.req("PATCH", ourl, {"status": "paid", "paid_date": o["due_date"]})[1]
        check(not fixed["is_overdue"] and fixed["due_date"] == o["due_date"], "исправление даты убрало просрочку, срок не изменился (оплата в день срока — вовремя)")
        user.req("PATCH", ourl, {"status": "unpaid"})
    else:
        print("  -- нет просроченных периодов для проверки исправления даты (сид выключен?)")
    user.req("PATCH", url, {"status": "paid"})
    occ = user.req("GET", f"/api/v1/payment-occurrences?recurring_payment_id={pid}&sort=due_date")[1]["items"]
    check(occ[0]["status"] == "paid" and occ[1]["id"] == second["id"] and occ[1]["status"] == "unpaid", "после оплаты следующий период со своим статусом, прошлый сохранён")

    print("\n6. Валюты и итоги отдельно по каждой")
    s = user.req("GET", "/api/v1/payments/summary")[1]
    check(sorted(c["currency"] for c in s["currencies"]) == ["EUR", "RUB", "USD"], "итоги по RUB, USD, EUR")
    check(admin.req("POST", "/api/v1/recurring-payments", {**body, "currency": "GBP"})[0] == 422, "чужая валюта -> 422")

    print("\n9. OpenAPI и Swagger")
    check(anon.req("GET", "/api/v1/openapi.json")[0] == 200, "/api/v1/openapi.json")
    check(anon.req("GET", "/api/v1/docs", raw=True)[0] == 200, "/api/v1/docs")

    print("\n10. Админ из .env не изменяется через API")
    me = admin.req("GET", "/api/v1/auth/me")[1]
    check(admin.req("PATCH", f"/api/v1/users/{me['id']}", {"password": "hacked1"})[0] == 403, "PATCH системного админа -> 403")
    check(admin.req("DELETE", f"/api/v1/users/{me['id']}")[0] == 403, "DELETE системного админа -> 403")
    check(admin.req("POST", "/api/v1/users", {"login": me["login"], "password": "123456"})[0] == 409, "пользователь с логином админа -> 409")
    check(all(u["login"] != me["login"] for u in admin.req("GET", "/api/v1/users")[1]), "системный админ не виден в /users")

    print("\nУдаление: история сохраняется")
    check(admin.req("DELETE", f"/api/v1/recurring-payments/{pid}")[0] == 204, "DELETE -> 204")
    left = user.req("GET", f"/api/v1/payment-occurrences?recurring_payment_id={pid}")[1]["items"]
    check(len(left) == 1 and left[0]["recurring_payment_deleted"] and left[0]["status"] == "paid", "оплаченный период остался с признаком «платёж прекращён», будущий удалён")
    check(admin.req("DELETE", f"/api/v1/recurring-payments/{pid}")[0] == 404, "повторный DELETE -> 404")

    print(f"\nИтог: {'ВСЁ ЗЕЛЁНОЕ' if not failures else f'ошибок: {len(failures)}'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
