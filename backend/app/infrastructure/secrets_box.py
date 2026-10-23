"""Шифрование секретов в БД (Fernet, ключ выводится из SECRET_KEY)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    def __init__(self, secret_key: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(("ik-secret-box:" + secret_key).encode()).digest())
        self._f = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken:
            return None
