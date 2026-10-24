"""Чек с QR → оплата отмечена сама (API и бот)."""

import asyncio
import io

import qrcode
from PIL import Image, ImageDraw

from tests.integration.helpers import create_payment, occurrences_of

QR = "t=20261020T1530&s=55000.00&fn=7380440700076549&i=12345&fp=2981623349&n=1"


def receipt_png(qr_text=QR, photo_like=True) -> bytes:
    """Похоже на фото чека: белый лист с текстом и QR в углу."""
    qr = qrcode.make(qr_text, box_size=6).get_image().convert("RGB")
    sheet = Image.new("RGB", (900, 1400), "white") if photo_like else qr
    if photo_like:
        d = ImageDraw.Draw(sheet)
        for y in range(60, 700, 40):
            d.text((60, y), "ООО Арендодатель   кассовый чек   55 000.00", fill="black")
        sheet.paste(qr, (250, 800))
        sheet = sheet.rotate(3, expand=True, fillcolor="gray")
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue()


def receipt_pdf() -> bytes:
    img = Image.open(io.BytesIO(receipt_png(photo_like=False)))
    buf = io.BytesIO()
    img.save(buf, "PDF")
    return buf.getvalue()


def scan(client, data, name="check.png", mime="image/png"):
    return client.post("/api/v1/receipts/scan", files={"file": (name, data, mime)})


def test_photo_of_receipt_marks_matching_period_paid(admin, user):
    p = create_payment(admin, title="Аренда", amount="55000", currency="RUB", first_due_date="2026-10-18")
    create_payment(admin, title="Другое", amount="55000", currency="RUB", first_due_date="2026-12-30")
    r = scan(user, receipt_png())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "matched" and body["receipt"]["amount"] == "55000.00"
    occ = body["occurrence"]
    assert occ["recurring_payment_id"] == p["id"] and occ["due_date"] == "2026-10-18"
    assert occ["status"] == "paid" and occ["paid_date"] == "2026-10-20" and occ["overdue_days"] == 2
    assert occ["has_receipt"] is True
    rec = user.get(f"/api/v1/payment-occurrences/{occ['id']}/receipt").json()
    assert rec["mime"] == "image/png"
    # тот же чек второй раз не засчитывается
    again = scan(user, receipt_png()).json()
    assert again["status"] == "already_counted"
    assert [o["status"] for o in occurrences_of(admin, p["id"])].count("paid") == 1


def test_pdf_receipt(admin, user):
    create_payment(admin, title="Аренда", amount="55000", currency="RUB", first_due_date="2026-10-20")
    body = scan(user, receipt_pdf(), "receipt.pdf", "application/pdf").json()
    assert body["status"] == "matched" and body["occurrence"]["is_overdue"] is False


def test_no_matching_amount(admin, user):
    create_payment(admin, title="Аренда", amount="50000", currency="RUB", first_due_date="2026-10-20")
    body = scan(user, receipt_png()).json()
    assert body["status"] == "no_match" and "55\u00a0000,00" in body["message"]


def test_not_a_receipt(user):
    plain = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(plain, "PNG")
    assert scan(user, plain.getvalue()).json()["status"] == "not_receipt"
    other_qr = scan(user, receipt_png("https://example.com", photo_like=False)).json()
    assert other_qr["status"] == "not_receipt"
    assert scan(user, b"hello", "x.txt", "text/plain").status_code == 422


def test_refund_receipt_ignored(admin, user):
    create_payment(admin, title="Аренда", amount="55000", first_due_date="2026-10-20")
    body = scan(user, receipt_png(QR.replace("n=1", "n=2"))).json()
    assert body["status"] == "no_match" and "возврат" in body["message"]


def test_bot_photo_in_private(admin, user, regular_user, container):
    from app.services.telegram_updates import TelegramUpdateHandler
    from tests.worker.test_telegram_button import FakeTelegramClient

    admin.patch(f"/api/v1/users/{regular_user.id}", json={"telegram_user_id": 555})
    p = create_payment(admin, title="Аренда", amount="55000", first_due_date="2026-10-20")
    png = receipt_png()

    class Client(FakeTelegramClient):
        async def get_file(self, file_id):
            return {"file_path": f"photos/{file_id}.jpg"}

        async def download_file(self, path, max_bytes):
            return png

    client = Client()
    update = {"update_id": 1, "message": {"message_id": 7, "chat": {"id": 555, "type": "private"}, "from": {"id": 555},
                                          "photo": [{"file_id": "small"}, {"file_id": "big"}]}}
    asyncio.run(TelegramUpdateHandler(container, client).handle_update(update))
    assert "Оплата отмечена" in client.messages[0]["text"] and client.messages[0]["reply_to"] == 7
    occ = occurrences_of(admin, p["id"])[0]
    assert occ["status"] == "paid" and occ["paid_date"] == "2026-10-20"
    log = admin.get("/api/v1/audit-logs", params={"action": "occurrence.paid"}).json()["items"][0]
    assert log["actor_login"] == "ivan" and log["user_agent"] == "telegram-bot"
    # непривязанный аккаунт
    stranger = Client()
    update["message"]["from"]["id"] = 999
    update["message"]["chat"]["id"] = 999
    asyncio.run(TelegramUpdateHandler(container, stranger).handle_update(update))
    assert "привяжите Telegram" in stranger.messages[0]["text"]
