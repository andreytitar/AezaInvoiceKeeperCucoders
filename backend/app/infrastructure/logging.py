"""Структурированные JSON-логи с request_id и маскированием секретов."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_SECRET_PATTERNS = [
    re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}"),  # токен Telegram в URL
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),  # токен Telegram отдельно
    re.compile(r"(?i)(password|passwd|secret|token|authorization|cookie)([\"']?\s*[:=]\s*[\"']?)([^\s\"',;]+)"),
]


def mask_secrets(text: str) -> str:
    text = _SECRET_PATTERNS[0].sub("bot***", text)
    text = _SECRET_PATTERNS[1].sub("***", text)
    text = _SECRET_PATTERNS[2].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return text


class JsonFormatter(logging.Formatter):
    _RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "color_message"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            # метка времени лога — техническая, Clock здесь не нужен
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": mask_secrets(record.getMessage()),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value if isinstance(value, (int, float, bool)) or value is None else mask_secrets(str(value))
        if record.exc_info:
            payload["exc"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
