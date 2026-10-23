from __future__ import annotations

import threading

from app.infrastructure.channels.base import Notification, SendResult


class FakeChannel:
    """Канал для тестов: запоминает отправленные сообщения, умеет падать заданное число раз."""

    def __init__(self, name: str = "telegram", recipients: list[str] | None = None, fail_times: int = 0) -> None:
        self.name = name
        self._recipients = recipients if recipients is not None else ["-100500"]
        self.fail_times = fail_times
        self.sent: list[tuple[Notification, str]] = []
        self.attempts = 0
        self._lock = threading.Lock()

    def recipients(self) -> list[str]:
        return list(self._recipients)

    async def send(self, message: Notification, recipient: str) -> SendResult:
        with self._lock:
            self.attempts += 1
            if self.fail_times > 0:
                self.fail_times -= 1
                return SendResult(ok=False, error="fake failure")
            self.sent.append((message, recipient))
            return SendResult(ok=True, external_id=f"{recipient}:{len(self.sent)}")


class ExplodingChannel(FakeChannel):
    async def send(self, message: Notification, recipient: str) -> SendResult:
        self.attempts += 1
        raise RuntimeError("boom")
