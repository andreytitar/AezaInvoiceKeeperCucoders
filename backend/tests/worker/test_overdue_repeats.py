from datetime import date

from tests.integration.helpers import create_payment, occurrences_of
from tests.worker.test_reminders import tick


def test_overdue_repeats_every_3_days_until_paid(admin, user, container, clock, fake_channel):
    p = create_payment(admin, first_due_date="2026-10-26")  # напоминание сразу (24.10)
    assert len(fake_channel.sent) == 1
    for d in range(25, 32):  # 25.10 ... 31.10
        clock.set_today(date(2026, 10, d))
        tick(container)
        tick(container)
    # просрочка: 27.10 (1-й день) и 30.10 (4-й день)
    titles = [(m.kind, m.days_until_due) for m, _ in fake_channel.sent]
    assert titles == [("reminder", 2), ("overdue:0", -1), ("overdue:1", -4)]
    assert fake_channel.sent[1][0].actions  # кнопка «Оплачено» есть и в повторе
    oid = occurrences_of(admin, p["id"])[0]["id"]
    user.patch(f"/api/v1/payment-occurrences/{oid}", json={"status": "paid", "paid_date": "2026-10-31"})
    clock.set_today(date(2026, 11, 3))
    tick(container)
    assert len(fake_channel.sent) == 3


def test_no_repeat_same_day_as_first_reminder(admin, container, fake_channel):
    create_payment(admin, first_due_date="2026-10-10")  # уже просрочен на 14 дней
    tick(container)
    assert [m.kind for m, _ in fake_channel.sent] == ["reminder"]


def test_repeats_disabled(admin, container, clock, fake_channel):
    container.settings.overdue_remind_every_days = 0
    create_payment(admin, first_due_date="2026-10-26")
    clock.set_today(date(2026, 10, 30))
    tick(container)
    assert len(fake_channel.sent) == 1


def test_deleted_payment_no_repeats(admin, container, clock, fake_channel):
    p = create_payment(admin, first_due_date="2026-10-20")
    admin.delete(f"/api/v1/recurring-payments/{p['id']}")
    clock.set_today(date(2026, 10, 28))
    tick(container)
    assert len(fake_channel.sent) == 1
