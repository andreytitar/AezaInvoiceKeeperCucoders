"""Текст до кнопки «Старт» и меню команд. В Telegram не ходит сам по себе.

Имена команд совпадают с разбором в TelegramUpdateHandler.handle_message:
/start, /join, /bind, /help, /site, /topay, /overdue, /week, /paid, /summary, /add.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

log = logging.getLogger("app.telegram_profile")

SHORT_DESCRIPTION = "Напоминает об аренде, подписках и серверах за 3 дня до срока."

DESCRIPTION = (
    "Invoice Keeper напоминает команде о регулярных платежах: "
    "за три дня до срока пишет, что оплатить, что уже оплачено и что просрочено. "
    "Нажмите Start."
)

# Пример только внутри скобок и не в начале строки. Пометку роли сюда не ставим.
ADD_DESCRIPTION = "Добавить платёж одной фразой (только админ)"

COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Меню и привязка аккаунта"),
    ("topay", "Что и когда оплатить"),
    ("overdue", "Просроченные платежи"),
    ("week", "Платежи на 7 дней"),
    ("paid", "Оплаченное за 30 дней"),
    ("summary", "Итоги по валютам"),
    ("add", ADD_DESCRIPTION),
    ("join", "Вступите в команду по коду приглашения"),
    ("bind", "Подключите групповой чат для напоминаний"),
    ("site", "Откройте панель в браузере"),
    ("help", "Узнайте, что умеет бот"),
)

_COMMAND_NAME = re.compile(r"[a-z0-9_]{1,32}")


class _TelegramApi(Protocol):
    async def set_my_short_description(self, short_description: str) -> Any: ...

    async def set_my_description(self, description: str) -> Any: ...

    async def set_my_commands(self, commands: list[tuple[str, str]]) -> Any: ...


def profile_payloads() -> dict[str, dict[str, Any]]:
    """Тела setMyShortDescription, setMyDescription и setMyCommands. Сеть не вызывается."""
    if len(SHORT_DESCRIPTION) > 120:
        raise ValueError("setMyShortDescription длиннее 120 символов")
    if len(DESCRIPTION) > 512:
        raise ValueError("setMyDescription длиннее 512 символов")
    commands: list[dict[str, str]] = []
    seen: set[str] = set()
    for command, description in COMMANDS:
        if _COMMAND_NAME.fullmatch(command) is None:
            raise ValueError(f"недопустимое имя команды: {command}")
        if command in seen:
            raise ValueError(f"команда повторяется: {command}")
        seen.add(command)
        if not description or len(description) > 256:
            raise ValueError(f"описание /{command} пустое или длиннее 256 символов")
        commands.append({"command": command, "description": description})
    return {
        "setMyShortDescription": {"short_description": SHORT_DESCRIPTION},
        "setMyDescription": {"description": DESCRIPTION},
        "setMyCommands": {"commands": commands},
    }


async def apply_telegram_profile(client: _TelegramApi) -> None:
    """Ставит описание и меню один раз. Ошибка пишется в лог и не останавливает воркер."""
    try:
        payloads = profile_payloads()
    except Exception as exc:  # noqa: BLE001
        log.warning("профиль бота: %s", exc)
        return
    short = payloads["setMyShortDescription"]["short_description"]
    description = payloads["setMyDescription"]["description"]
    commands = [(item["command"], item["description"]) for item in payloads["setMyCommands"]["commands"]]
    steps = (
        ("setMyShortDescription", lambda: client.set_my_short_description(short)),
        ("setMyDescription", lambda: client.set_my_description(description)),
        ("setMyCommands", lambda: client.set_my_commands(commands)),
    )
    for method, start in steps:
        try:
            await start()
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: %s", method, exc)
