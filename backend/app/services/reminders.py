"""Напоминания: постановка в очередь (ReminderService) и доставка (DeliveryDispatcher).

Гарантии:
- без дублей: UNIQUE(occurrence_id, channel, recipient, kind) + INSERT ... ON CONFLICT DO NOTHING;
- параллельные worker'ы: захват пачки через SELECT ... FOR UPDATE SKIP LOCKED;
- перед отправкой повторно проверяется, что период не оплачен и платёж не удалён;
- `sent` ставится только после успешного ответа канала, ошибка -> `failed` с backoff, затем `dead`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.domain.clock import Clock
from app.domain.reminder_policy import days_until, overdue_repeat_bucket, reminder_window_end, should_remind
from app.infrastructure.channels.base import Action, ChannelRegistry, Notification, SendResult
from app.models import DeliveryKind, DeliveryStatus, NotificationDelivery, PaymentOccurrence
from app.repositories.reminders import ReminderRepository
from app.services.audit import AuditService
from app.services.team_delivery import clear_dead_chat, is_dead_chat_error, recipients_for

log = logging.getLogger("app.reminders")

BACKOFF_MINUTES = (1, 5, 15, 60)


def backoff_delay(attempts: int) -> timedelta:
    idx = min(max(attempts, 1), len(BACKOFF_MINUTES)) - 1
    return timedelta(minutes=BACKOFF_MINUTES[idx])


class ReminderService:
    def __init__(self, db: DbSession, clock: Clock, settings: Settings, channels: ChannelRegistry) -> None:
        self.db = db
        self.clock = clock
        self.settings = settings
        self.channels = channels
        self.repo = ReminderRepository(db)

    def scan(self, payment_id: uuid.UUID | None = None, commit: bool = True, team_id: uuid.UUID | None = None) -> int:
        """Находит периоды, по которым пора напомнить, и ставит доставки в очередь. Идемпотентно."""
        today = self.clock.today()
        now = self.clock.now()
        days = self.settings.reminder_days_before
        created = 0
        for occ in self.repo.candidates(reminder_window_end(today, days), payment_id, team_id):
            if not should_remind(
                due_date=occ.due_date,
                is_paid=occ.is_paid,
                payment_deleted=occ.payment.deleted_at is not None,
                today=today,
                days_before=days,
            ):
                continue
            for channel in self.channels.all():
                for recipient in recipients_for(self.db, self.settings, channel, occ):
                    if self.repo.enqueue(occ.id, channel.name, recipient, DeliveryKind.REMINDER.value, now):
                        created += 1
        created += self.scan_overdue_repeats(today, now, team_id)
        if commit:
            self.db.commit()
        if created:
            log.info("Поставлено напоминаний в очередь: %s", created)
        return created

    def scan_overdue_repeats(self, today, now, team_id: uuid.UUID | None = None) -> int:
        """Повторные напоминания о просрочке раз в OVERDUE_REMIND_EVERY_DAYS дней (вебхуки — отдельным событием).
        Первый повтор не уходит в тот же день, что и основное напоминание."""
        s = self.settings
        if s.overdue_remind_every_days <= 0:
            return 0
        created = 0
        for occ in self.repo.candidates(today - timedelta(days=1), team_id=team_id):
            bucket = overdue_repeat_bucket((today - occ.due_date).days, s.overdue_remind_every_days, s.overdue_remind_max)
            if bucket is None or occ.payment.deleted_at is not None:
                continue
            for channel in self.channels.all():
                if channel.name == "webhook":
                    continue
                for recipient in recipients_for(self.db, self.settings, channel, occ):
                    if not self.repo.reminder_sent_before(occ.id, channel.name, recipient, now - timedelta(hours=12)):
                        continue
                    if self.repo.enqueue(occ.id, channel.name, recipient, f"overdue:{bucket}", now):
                        created += 1
        return created


@dataclass
class DispatchStats:
    sent: int = 0
    failed: int = 0
    dead: int = 0
    cancelled: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.failed + self.dead + self.cancelled


class DeliveryDispatcher:
    def __init__(
        self,
        session_factory: sessionmaker[DbSession],
        clock: Clock,
        settings: Settings,
        channels: ChannelRegistry,
        notification_builders: dict | None = None,
        on_sent=None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock
        self.settings = settings
        self.channels = channels
        self.builders = notification_builders or {}
        self.on_sent = on_sent  # хук для аудита и т. п. (этап 8)

    def build_notification(self, d: NotificationDelivery, occ: PaymentOccurrence) -> Notification:
        is_reminder = d.kind == DeliveryKind.REMINDER.value or d.kind.startswith("overdue:")
        return Notification(
            occurrence_id=occ.id,
            title=occ.title_snapshot,
            amount=occ.amount_snapshot,
            currency=occ.currency_snapshot.value,
            due_date=occ.due_date,
            kind=d.kind,
            days_until_due=days_until(occ.due_date, self.clock.today()),
            actions=(Action("Оплачено", f"paid:{occ.id}"),) if is_reminder else (),
            extra={
                "delivery_id": str(d.id),
                "status": "paid" if occ.is_paid else "unpaid",
                "paid_date": occ.paid_date.isoformat() if occ.paid_date else None,
                "recurring_payment_id": str(occ.recurring_payment_id),
            },
        )

    def _still_relevant(self, d: NotificationDelivery, occ: PaymentOccurrence | None) -> bool:
        if occ is None:
            return False
        if d.kind in (DeliveryKind.REMINDER.value, "payment.overdue") or d.kind.startswith("overdue:"):
            # напоминание и «просрочено» неактуальны, если период оплачен или платёж удалён
            return not occ.is_paid and occ.payment.deleted_at is None
        return True

    async def run(self, batch_size: int = 50, max_batches: int = 20) -> DispatchStats:
        stats = DispatchStats()
        with self.session_factory() as db:
            stale_before = self.clock.now() - timedelta(seconds=self.settings.delivery_stale_seconds)
            released = ReminderRepository(db).release_stale(stale_before)
            db.commit()
            if released:
                log.warning("Возвращено зависших доставок в очередь: %s", released)
        for _ in range(max_batches):
            with self.session_factory() as db:
                claimed = [d.id for d in ReminderRepository(db).claim_batch(self.clock.now(), batch_size)]
                db.commit()
            if not claimed:
                break
            for delivery_id in claimed:
                await self._deliver(delivery_id, stats)
        if stats.total:
            log.info(
                "Рассылка: отправлено %s, ошибок %s, dead %s, отменено %s",
                stats.sent, stats.failed, stats.dead, stats.cancelled,
            )
        return stats

    async def _deliver(self, delivery_id: uuid.UUID, stats: DispatchStats) -> None:
        # 1. Подготовка: повторная проверка актуальности (период мог быть оплачен после постановки в очередь)
        with self.session_factory() as db:
            d = ReminderRepository(db).get(delivery_id)
            if d is None or d.status != DeliveryStatus.SENDING:
                return
            occ = db.get(PaymentOccurrence, d.occurrence_id)
            channel = self.channels.get(d.channel)
            if not self._still_relevant(d, occ):
                d.status = DeliveryStatus.CANCELLED
                d.last_error = "cancelled: paid or payment deleted"
                d.locked_at = None
                db.commit()
                stats.cancelled += 1
                return
            if channel is None:
                d.status = DeliveryStatus.DEAD
                d.last_error = f"channel {d.channel!r} is not configured"
                d.locked_at = None
                db.commit()
                stats.dead += 1
                log.error("Канал %s не настроен, доставка %s -> dead", d.channel, d.id)
                return
            builder = self.builders.get(d.kind, None)
            message = builder(db, d, occ) if builder else self.build_notification(d, occ)
            recipient = d.recipient

        # 2. Отправка (вне транзакции)
        try:
            result = await channel.send(message, recipient)
        except Exception as exc:  # noqa: BLE001 — сбой одного канала не блокирует остальные
            log.exception("Канал %s упал при отправке", d.channel)
            result = SendResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        # 3. Фиксация результата
        with self.session_factory() as db:
            d = ReminderRepository(db).get(delivery_id)
            if d is None:
                return
            now = self.clock.now()
            d.locked_at = None
            if result.ok:
                d.status = DeliveryStatus.SENT
                d.sent_at = now
                d.last_error = None
                d.external_id = result.external_id
                stats.sent += 1
            elif d.channel == "telegram" and is_dead_chat_error(result.error):
                clear_dead_chat(db, d.recipient)
                d.status = DeliveryStatus.DEAD
                d.last_error = (result.error or "chat unavailable")[:2000]
                stats.dead += 1
                log.warning("Чат %s недоступен, доставка %s закрыта, привязка снята", d.recipient, d.id)
            elif d.attempts >= self.settings.delivery_max_attempts:
                d.status = DeliveryStatus.DEAD
                d.last_error = (result.error or "unknown error")[:2000]
                stats.dead += 1
                log.error(
                    "АЛЕРТ: доставка %s (%s -> %s) не удалась после %s попыток: %s",
                    d.id, d.channel, d.recipient, d.attempts, d.last_error,
                )
            else:
                d.status = DeliveryStatus.FAILED
                d.last_error = (result.error or "unknown error")[:2000]
                d.next_attempt_at = now + backoff_delay(d.attempts)
                stats.failed += 1
                log.warning("Ошибка доставки %s, попытка %s: %s", d.id, d.attempts, d.last_error)
            if d.status in (DeliveryStatus.SENT, DeliveryStatus.DEAD):
                AuditService(db, self.clock).log(
                    "notification.sent" if d.status == DeliveryStatus.SENT else "notification.dead",
                    entity_type="payment_occurrence",
                    entity_id=d.occurrence_id,
                    after={"channel": d.channel, "recipient": d.recipient, "kind": d.kind, "attempts": d.attempts, "error": d.last_error},
                    actor_login="worker",
                )
            db.commit()
            if result.ok and self.on_sent:
                self.on_sent(db, d, message)


def make_dispatcher(container) -> DeliveryDispatcher:
    builders = container.extras.get("notification_builders")
    on_sent = container.extras.get("on_delivery_sent")
    return DeliveryDispatcher(
        container.session_factory, container.clock, container.settings, container.channels, builders, on_sent
    )


async def dispatch_now(container) -> None:
    """Немедленная рассылка (после создания платежа). Безопасна параллельно с worker."""
    try:
        await make_dispatcher(container).run()
    except Exception:  # noqa: BLE001
        log.exception("Немедленная рассылка не удалась, её доделает worker")
