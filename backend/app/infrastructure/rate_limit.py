"""Ограничение частоты неудачных попыток входа (в памяти процесса api).

Ключ — (IP, логин). Достаточно для одного экземпляра api; для горизонтального масштабирования
вынести в Redis/БД (см. README).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, ip: str, login: str) -> int | None:
        """Секунды до следующей разрешённой попытки или None, если вход разрешён."""
        now = time.monotonic()  # монотонные часы процесса, не бизнес-время
        with self._lock:
            q = self._prune((ip, login.lower()), now)
            if len(q) >= self.max_attempts:
                return max(1, int(self.window - (now - q[0])))
        return None

    def register_failure(self, ip: str, login: str) -> None:
        with self._lock:
            self._failures[(ip, login.lower())].append(time.monotonic())

    def reset(self, ip: str, login: str) -> None:
        with self._lock:
            self._failures.pop((ip, login.lower()), None)
