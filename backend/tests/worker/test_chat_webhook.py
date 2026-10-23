import json

import httpx

from app.infrastructure.channels.base import ChannelRegistry
from app.infrastructure.channels.chat_webhook import ChatWebhookChannel, detect_format
from app.infrastructure.channels.registry import build_channels
from tests.integration.helpers import create_payment
from tests.worker.test_reminders import deliveries, tick


def chat(url, rec, fail=0):
    state = {"fail": fail}

    def handler(request):
        if state["fail"]:
            state["fail"] -= 1
            return httpx.Response(500)
        rec.append(json.loads(request.content))
        return httpx.Response(200)

    return ChatWebhookChannel(url, allow_private=True, transport=httpx.MockTransport(handler))


def test_detect_format():
    assert detect_format("https://discord.com/api/webhooks/1/x", "auto") == "discord"
    assert detect_format("https://hooks.slack.com/services/T/B/x", "auto") == "slack"
    assert detect_format("https://mm.example.com/hooks/abc", "auto") == "mattermost"
    assert detect_format("https://x.y/z", "discord") == "discord"


def test_slack_message(admin, container):
    rec = []
    container.channels = ChannelRegistry([chat("https://hooks.slack.com/services/T/B/secret", rec)])
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    assert len(rec) == 1
    text = rec[0]["text"]
    assert "*Сервер*" in text and "25,00 $ (USD)" in text and "26.10.2026" in text
    d = deliveries(container)[0]
    assert d.channel == "chat" and "secret" not in d.recipient  # токен URL не попадает в БД


def test_discord_message_and_retry(admin, container, clock):
    rec = []
    container.channels = ChannelRegistry([chat("https://discord.com/api/webhooks/1/tok", rec, fail=1)])
    create_payment(admin, title="Подписка", amount="9.99", currency="EUR", first_due_date="2026-10-25")
    assert rec == []
    clock.advance(minutes=2)
    tick(container)
    tick(container)
    assert len(rec) == 1 and "**Подписка**" in rec[0]["content"] and rec[0]["allowed_mentions"] == {"parse": []}


def test_registered_only_when_configured(settings):
    assert "chat" not in build_channels(settings).names()
    settings.chat_webhook_url = "https://hooks.slack.com/services/T/B/x"
    assert "chat" in build_channels(settings).names()
