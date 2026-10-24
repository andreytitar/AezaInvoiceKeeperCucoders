"""Напоминания с FakeChannel и FixedClock: окно в 3 дня, дубли, сбои, параллельность, рестарт."""

import asyncio
import threading
from datetime import date, timedelta

from sqlalchemy import select, update

from app.infrastructure.channels.base import ChannelRegistry
from app.models import DeliveryStatus, NotificationDelivery
from app.services.occurrences import OccurrenceGenerator
from app.services.reminders import ReminderService, make_dispatcher
from app.worker import Worker
from tests.fakes import ExplodingChannel, FakeChannel
from tests.integration.helpers import create_payment, occurrences_of


def tick(container):
    asyncio.run(Worker(container).tick())


def deliveries(container):
    with container.session_factory() as db:
        return list(db.scalars(select(NotificationDelivery).order_by(NotificationDelivery.created_at)))


def test_late_added_payment_reminds_immediately(admin, fake_channel):
    # срок через 2 дня: напоминание уходит сразу при создании (фоновая задача API)
    create_payment(admin, title="Сервер", amount="25", currency="USD", first_due_date="2026-10-26")
    assert len(fake_channel.sent) == 1
    msg, recipient = fake_channel.sent[0]
    assert (msg.title, str(msg.amount), msg.currency, msg.due_date) == ("Сервер", "25.00", "USD", date(2026, 10, 26))
    assert recipient == "-100500"


def test_far_payment_not_reminded_until_three_days_before(admin, container, clock, fake_channel):
    create_payment(admin, first_due_date="2026-11-05")
    tick(container)
    assert fake_channel.sent == []
    clock.set_today(date(2026, 11, 1))  # 4 дня
    tick(container)
    assert fake_channel.sent == []
    clock.set_today(date(2026, 11, 2))  # 3 дня — минимум
    tick(container)
    assert len(fake_channel.sent) == 1
    assert fake_channel.sent[0][0].days_until_due == 3


def test_no_duplicates_on_repeated_checks(admin, container, clock, fake_channel):
    container.settings.overdue_remind_every_days = 0  # повторы о просрочке проверяются отдельно
    create_payment(admin, first_due_date="2026-10-25")
    for _ in range(3):
        tick(container)
    clock.advance(days=1)
    tick(container)  # день срока
    clock.advance(days=3)
    tick(container)  # просрочка
    assert len(fake_channel.sent) == 1
    assert [d.status for d in deliveries(container)] == [DeliveryStatus.SENT]


def test_restart_does_not_resend(admin, container, fake_channel):
    create_payment(admin, first_due_date="2026-10-25")
    # «рестарт»: новые экземпляры worker, реестра и канала
    new_channel = FakeChannel()
    container.channels = ChannelRegistry([new_channel])
    tick(container)
    tick(container)
    assert len(fake_channel.sent) == 1 and new_channel.sent == []


def test_paid_period_not_reminded(admin, user, container, fake_channel):
    p = create_payment(admin, first_due_date="2026-11-05")
    first = occurrences_of(user, p["id"])[0]
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "paid"})
    container.clock.set_today(date(2026, 11, 4))
    tick(container)
    assert fake_channel.sent == []


def test_paid_after_enqueue_cancels_before_sending(admin, user, container, clock):
    failing = FakeChannel(fail_times=1)
    container.channels = ChannelRegistry([failing])
    p = create_payment(admin, first_due_date="2026-10-25")  # первая попытка падает -> failed
    assert [d.status for d in deliveries(container)] == [DeliveryStatus.FAILED]
    first = occurrences_of(user, p["id"])[0]
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "paid"})
    clock.advance(minutes=2)
    tick(container)
    assert failing.sent == []
    assert [d.status for d in deliveries(container)] == [DeliveryStatus.CANCELLED]


def test_unpaid_again_after_cancel_reminds(admin, user, container, clock):
    failing = FakeChannel(fail_times=1)
    container.channels = ChannelRegistry([failing])
    p = create_payment(admin, first_due_date="2026-10-25")
    first = occurrences_of(user, p["id"])[0]
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "paid"})
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "unpaid"})
    tick(container)
    assert len(failing.sent) == 1


def test_paid_after_sent_no_repeat(admin, user, container, clock, fake_channel):
    p = create_payment(admin, first_due_date="2026-10-25")
    assert len(fake_channel.sent) == 1
    first = occurrences_of(user, p["id"])[0]
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "paid"})
    user.patch(f"/api/v1/payment-occurrences/{first['id']}", json={"status": "unpaid"})
    tick(container)
    assert len(fake_channel.sent) == 1


def test_deleted_payment_never_reminds(admin, container, clock, fake_channel):
    # просроченный период удалённого платежа остаётся в истории, но не напоминает
    container.channels = ChannelRegistry([fake_channel])
    failing = FakeChannel(fail_times=10)
    container.channels = ChannelRegistry([failing])
    p = create_payment(admin, first_due_date="2026-10-20")
    admin.delete(f"/api/v1/recurring-payments/{p['id']}")
    container.channels = ChannelRegistry([fake_channel])
    for days in (0, 1, 30, 60):
        clock.set_today(date(2026, 10, 24) + timedelta(days=days))
        tick(container)
    assert fake_channel.sent == []
    assert {d.status for d in deliveries(container)} == {DeliveryStatus.CANCELLED}


def test_send_failure_retries_with_backoff_without_duplicates(admin, container, clock):
    failing = FakeChannel(fail_times=2)
    container.channels = ChannelRegistry([failing])
    create_payment(admin, first_due_date="2026-10-25")
    d = deliveries(container)[0]
    assert d.status == DeliveryStatus.FAILED and d.attempts == 1
    assert d.next_attempt_at == clock.now() + timedelta(minutes=1)
    tick(container)  # backoff ещё не прошёл
    assert failing.attempts == 1
    clock.advance(minutes=1, seconds=1)
    tick(container)
    d = deliveries(container)[0]
    assert d.status == DeliveryStatus.FAILED and d.attempts == 2
    assert d.next_attempt_at == clock.now() + timedelta(minutes=5)
    clock.advance(minutes=5, seconds=1)
    tick(container)
    assert len(failing.sent) == 1
    assert [x.status for x in deliveries(container)] == [DeliveryStatus.SENT]


def test_dead_after_max_attempts(admin, container, clock, caplog):
    failing = FakeChannel(fail_times=100)
    container.channels = ChannelRegistry([failing])
    create_payment(admin, first_due_date="2026-10-25")
    for _ in range(10):
        clock.advance(hours=2)
        tick(container)
    d = deliveries(container)[0]
    assert d.status == DeliveryStatus.DEAD and d.attempts == container.settings.delivery_max_attempts
    assert failing.attempts == container.settings.delivery_max_attempts


def test_one_channel_failure_does_not_block_others(admin, container):
    good = FakeChannel(name="good")
    bad = ExplodingChannel(name="bad")
    container.channels = ChannelRegistry([bad, good])
    create_payment(admin, first_due_date="2026-10-25")
    assert len(good.sent) == 1
    statuses = {d.channel: d.status for d in deliveries(container)}
    assert statuses == {"good": DeliveryStatus.SENT, "bad": DeliveryStatus.FAILED}


def test_parallel_workers_do_not_duplicate(admin, container, clock, fake_channel):
    container.channels = ChannelRegistry([FakeChannel(fail_times=0, recipients=[])])  # без отправки при создании
    for i in range(5):
        create_payment(admin, title=f"P{i}", first_due_date="2026-10-25")
    container.channels = ChannelRegistry([fake_channel])
    errors = []
    barrier = threading.Barrier(4)

    def run():
        try:
            barrier.wait()
            with container.session_factory() as db:
                ReminderService(db, clock, container.settings, container.channels).scan()
            asyncio.run(make_dispatcher(container).run(batch_size=2))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(m.title for m, _ in fake_channel.sent) == ["P0", "P1", "P2", "P3", "P4"]
    assert len(deliveries(container)) == 5


def test_stale_sending_is_released(admin, container, clock, fake_channel):
    container.channels = ChannelRegistry([FakeChannel(recipients=[])])
    create_payment(admin, first_due_date="2026-10-25")
    container.channels = ChannelRegistry([fake_channel])
    with container.session_factory() as db:
        ReminderService(db, clock, container.settings, container.channels).scan()
        db.execute(update(NotificationDelivery).values(status=DeliveryStatus.SENDING, locked_at=clock.now()))
        db.commit()
    tick(container)
    assert fake_channel.sent == []  # ещё не протухла
    clock.advance(seconds=container.settings.delivery_stale_seconds + 1)
    tick(container)
    assert len(fake_channel.sent) == 1


def test_overdue_period_reminded_once(admin, container, fake_channel):
    create_payment(admin, first_due_date="2026-10-01")
    assert len(fake_channel.sent) == 1
    assert fake_channel.sent[0][0].days_until_due == -23


def test_generation_in_tick_keeps_next_period(admin, container, clock):
    p = create_payment(admin, first_due_date="2026-10-25")
    clock.set_today(date(2026, 12, 1))
    tick(container)
    assert [o["due_date"] for o in occurrences_of(admin, p["id"])][-1] == "2026-12-25"


def test_heartbeat_written(container, anon):
    assert anon.get("/api/v1/health").json()["worker"]["alive"] is False
    tick(container)
    assert anon.get("/api/v1/health").json()["worker"]["alive"] is True


def test_generator_idempotent_concurrently(admin, container, clock):
    p = create_payment(admin, first_due_date="2026-10-25")
    clock.set_today(date(2027, 2, 1))
    errs = []

    def gen():
        try:
            with container.session_factory() as db:
                OccurrenceGenerator(db, clock).ensure_all()
        except Exception as exc:  # noqa: BLE001
            errs.append(exc)

    ts = [threading.Thread(target=gen) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errs == []
    dates = [o["due_date"] for o in occurrences_of(admin, p["id"])]
    assert len(dates) == len(set(dates))
