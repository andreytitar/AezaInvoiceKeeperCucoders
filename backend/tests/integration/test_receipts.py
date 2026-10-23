from tests.integration.helpers import create_payment, occurrences_of

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%fake\n"


def _occ(admin):
    p = create_payment(admin, first_due_date="2026-10-20")
    return occurrences_of(admin, p["id"])[0]["id"]


def url(oid):
    return f"/api/v1/payment-occurrences/{oid}/receipt"


def test_attach_link_and_file_then_download(admin, user, anon):
    oid = _occ(admin)
    r = user.put(url(oid), data={"url": "https://bank.example/receipt/42"})
    assert r.status_code == 200 and r.json()["url"] == "https://bank.example/receipt/42" and r.json()["file_url"] is None
    r = user.put(url(oid), files={"file": ("чек.png", PNG, "image/png")})
    body = r.json()
    assert r.status_code == 200 and body["url"] == "https://bank.example/receipt/42"  # ссылка сохранилась
    assert body["mime"] == "image/png" and body["size"] == len(PNG) and body["file_name"] == "чек.png"
    d = user.get(body["file_url"])
    assert d.status_code == 200 and d.content == PNG and d.headers["content-type"] == "image/png"
    assert d.headers["x-content-type-options"] == "nosniff"
    assert anon.get(body["file_url"]).status_code == 401
    occ = user.get(f"/api/v1/payment-occurrences/{oid}").json()
    assert occ["has_receipt"] is True


def test_type_checked_by_content_not_extension(admin, user):
    oid = _occ(admin)
    r = user.put(url(oid), files={"file": ("evil.pdf", b"<script>alert(1)</script>", "application/pdf")})
    assert r.status_code == 422
    r = user.put(url(oid), files={"file": ("doc.txt", PDF, "text/plain")})
    assert r.status_code == 200 and r.json()["mime"] == "application/pdf"


def test_size_limit(admin, user, container):
    oid = _occ(admin)
    big = PNG + b"\x00" * (5 * 1024 * 1024)
    r = user.put(url(oid), files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_url_validation(admin, user):
    oid = _occ(admin)
    for bad in ("javascript:alert(1)", "ftp://x.y/z", "not a url", "http://"):
        assert user.put(url(oid), data={"url": bad}).status_code == 422, bad
    assert user.put(url(oid), data={}).status_code == 422


def test_random_file_name_and_replace_deletes_old(admin, user, container):
    from pathlib import Path

    oid = _occ(admin)
    user.put(url(oid), files={"file": ("../../etc/passwd.png", PNG, "image/png")})
    files = list(Path(container.settings.uploads_dir).iterdir())
    assert len(files) == 1 and "passwd" not in files[0].name and len(files[0].stem) == 32
    user.put(url(oid), files={"file": ("b.pdf", PDF, "application/pdf")})
    files2 = list(Path(container.settings.uploads_dir).iterdir())
    assert len(files2) == 1 and files2[0].suffix == ".pdf"


def test_delete_and_audit(admin, user, container):
    from pathlib import Path

    oid = _occ(admin)
    user.put(url(oid), files={"file": ("a.png", PNG, "image/png")})
    assert user.delete(url(oid)).status_code == 204
    assert user.get(url(oid)).status_code == 404
    assert user.delete(url(oid)).status_code == 404
    assert list(Path(container.settings.uploads_dir).iterdir()) == []
    actions = [i["action"] for i in admin.get("/api/v1/audit-logs", params={"action": "receipt."}).json()["items"]]
    assert actions == ["receipt.delete", "receipt.upsert"]


def test_unknown_occurrence_404(user):
    assert user.put(url("00000000-0000-0000-0000-000000000000"), data={"url": "https://a.b/c"}).status_code == 404
