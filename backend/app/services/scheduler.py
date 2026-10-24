"""Одна итерация фоновых проверок. Её вызывает тик worker и кнопка «Проверить сейчас» (admin)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.services.occurrences import OccurrenceGenerator
from app.services.reminders import ReminderService, make_dispatcher
from app.services.webhooks import WebhookEvents


@dataclass
class CheckStats:
    periods_created: int = 0
    reminders_queued: int = 0
    overdue_events_queued: int = 0
    sent: int = 0
    failed: int = 0
    dead: int = 0
    cancelled: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


async def run_checks(c) -> CheckStats:
    """Идемпотентно: генерация периодов -> постановка напоминаний и событий -> доставка."""
    stats = CheckStats()
    with c.session_factory() as db:
        stats.periods_created = OccurrenceGenerator(db, c.clock).ensure_all()
    with c.session_factory() as db:
        stats.reminders_queued = ReminderService(db, c.clock, c.settings, c.channels).scan()
    with c.session_factory() as db:
        stats.overdue_events_queued = WebhookEvents(db, c.clock).scan_overdue()
    d = await make_dispatcher(c).run()
    stats.sent, stats.failed, stats.dead, stats.cancelled = d.sent, d.failed, d.dead, d.cancelled
    return stats
