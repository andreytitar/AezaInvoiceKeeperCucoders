"""Хранение файлов чеков в volume. Имена случайные, тип определяется по содержимому."""

from __future__ import annotations

import secrets
from pathlib import Path

SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"%PDF-", "application/pdf", "pdf"),
)


def sniff(data: bytes) -> tuple[str, str] | None:
    """(mime, ext) по магическим байтам или None, если тип не разрешён."""
    for magic, mime, ext in SIGNATURES:
        if data.startswith(magic):
            return mime, ext
    return None


class LocalStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir)

    def save(self, data: bytes, ext: str) -> str:
        self.base.mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(16)}.{ext}"
        (self.base / name).write_bytes(data)
        return name

    def path(self, name: str) -> Path:
        p = (self.base / name).resolve()
        if self.base.resolve() not in p.parents:
            raise ValueError("path traversal")
        return p

    def delete(self, name: str) -> None:
        try:
            self.path(name).unlink(missing_ok=True)
        except ValueError:
            pass
