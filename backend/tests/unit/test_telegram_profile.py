"""Описание бота и меню команд собираются локально, без запроса в Telegram."""

from __future__ import annotations

import asyncio
import logging
import re

from app.services.telegram_profile import apply_telegram_profile, profile_payloads

EXAMPLE = "аренда 55000 руб каждое 5-е"
HANDLERS = {"start", "join", "bind", "help", "site", "topay", "overdue", "week", "paid", "summary", "add"}


def _outside_parentheses(text: str) -> str:
    return re.sub(r"\([^()]*\)", "", text)


def test_add_command_description_puts_example_in_parentheses():
    commands = profile_payloads()["setMyCommands"]["commands"]
    add = next(item for item in commands if item["command"] == "add")
    description = add["description"]

    assert description.startswith("Добавить платёж")
    assert "фразой" in description
    assert EXAMPLE not in description
    assert description == "Добавить платёж одной фразой (только админ)"


def test_profile_payloads_are_the_prestart_screen_and_real_commands():
    payloads = profile_payloads()
    short = payloads["setMyShortDescription"]["short_description"]
    description = payloads["setMyDescription"]["description"]
    commands = payloads["setMyCommands"]["commands"]

    assert short == "Напоминает об аренде, подписках и серверах за 3 дня до срока."
    assert len(short) <= 120
    assert description == (
        "Invoice Keeper напоминает команде о регулярных платежах: "
        "за три дня до срока пишет, что оплатить, что уже оплачено и что просрочено. "
        "Нажмите Start."
    )
    assert len(description) <= 512
    assert {item["command"] for item in commands} == HANDLERS
    for item in commands:
        assert 1 <= len(item["description"]) <= 256
        assert not item["description"].startswith("аренда")
        assert "\n" not in item["description"]


def test_apply_profile_logs_errors_and_continues(caplog):
    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def set_my_short_description(self, short_description: str):
            self.calls.append(("setMyShortDescription", {"short_description": short_description}))
            raise RuntimeError("сеть недоступна")

        async def set_my_description(self, description: str):
            self.calls.append(("setMyDescription", {"description": description}))
            raise RuntimeError("сеть недоступна")

        async def set_my_commands(self, commands: list[tuple[str, str]]):
            payload = {"commands": [{"command": command, "description": text} for command, text in commands]}
            self.calls.append(("setMyCommands", payload))
            raise RuntimeError("сеть недоступна")

    client = Client()
    with caplog.at_level(logging.WARNING, logger="app.telegram_profile"):
        asyncio.run(apply_telegram_profile(client))

    assert [method for method, _ in client.calls] == [
        "setMyShortDescription",
        "setMyDescription",
        "setMyCommands",
    ]
    assert [payload for _, payload in client.calls] == list(profile_payloads().values())
    assert "setMyShortDescription" in caplog.text
    assert "setMyDescription" in caplog.text
    assert "setMyCommands" in caplog.text
    assert "сеть недоступна" in caplog.text
