"""Чтение QR-кодов с фото (PNG/JPG) и из PDF. Без сети и без ИИ: zxing-cpp + Pillow + pdfium."""

from __future__ import annotations

import io
import logging

import zxingcpp
from PIL import Image, ImageOps

from app.infrastructure.storage import sniff

log = logging.getLogger("app.qr")

MAX_PDF_PAGES = 3


def _decode_image(img: Image.Image) -> list[str]:
    img = ImageOps.exif_transpose(img).convert("RGB")
    variants = [img]
    w, h = img.size
    if max(w, h) > 2400:  # фото с телефона: уменьшаем, QR находится быстрее и надёжнее
        k = 2400 / max(w, h)
        variants.insert(0, img.resize((int(w * k), int(h * k))))
    if max(w, h) < 800:
        variants.append(img.resize((w * 2, h * 2)))
    variants.append(ImageOps.autocontrast(ImageOps.grayscale(img)))
    for v in variants:
        found = [r.text for r in zxingcpp.read_barcodes(v, formats=zxingcpp.BarcodeFormat.QRCode) if r.text]
        if found:
            return found
    return []


def read_qr_codes(data: bytes) -> list[str]:
    kind = sniff(data)
    if kind is None:
        return []
    mime, _ = kind
    try:
        if mime == "application/pdf":
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(data)
            out: list[str] = []
            for idx in range(min(len(pdf), MAX_PDF_PAGES)):
                out += _decode_image(pdf[idx].render(scale=2.5).to_pil())
                if out:
                    break
            return out
        return _decode_image(Image.open(io.BytesIO(data)))
    except Exception as exc:  # noqa: BLE001 — битый файл не должен ронять бота
        log.warning("Не удалось прочитать QR: %s", type(exc).__name__)
        return []
