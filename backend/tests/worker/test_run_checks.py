from datetime import date

from app.infrastructure.channels.base import ChannelRegistry
from tests.fakes import FakeChannel
from tests.integration.helpers import create_payment


def test_run_checks_button_sends_immediately(admin, container, clock, fake_channel):
    container.channels = ChannelRegistry([FakeChannel(recipients=[])])
    create_payment(admin, first_due_date="2026-11-05")
    container.channels = ChannelRegistry([fake_channel])
    clock.set_today(date(2026, 11, 2))
    r = admin.post("/api/v1/admin/run-checks")
    assert r.status_code == 200
    body = r.json()
    assert body["reminders_queued"] == 1 and body["sent"] == 1
    again = admin.post("/api/v1/admin/run-checks").json()
    assert again["reminders_queued"] == 0 and again["sent"] == 0  # идемпотентно
    assert len(fake_channel.sent) == 1
    assert admin.get("/api/v1/audit-logs", params={"action": "admin.run_checks"}).json()["total"] == 2
