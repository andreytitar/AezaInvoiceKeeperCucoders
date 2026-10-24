"""Еженедельная сводка в чат напоминаний команды: просрочено + ближайшие 7 дней.

Раз в неделю (DIGEST_WEEKDAY, DIGEST_HOUR в APP_TIMEZONE). Отправка ровно одна на команду:
ключ недели в app_meta захватывается до отправки и снимается, если отправка не удалась.
Получатель тот же, что у напоминаний: группа команды или личка администратора песочницы.
"""

from __future__ import annotations

import logging
import uuid
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.channels.telegram import LogTelegramChannel, TelegramChannel
from app.models import AppMeta
from app.repositories.teams import TeamRepository
from app.services.bot_answers import BotAnswers
from app.services.team_delivery import telegram_recipient

log = logging.getLogger("app.digest")


def digest_key(today, team_id) -> str:
    year, week, _ = today.isocalendar()
    return f"digest:{year}-W{week:02d}:{team_id}"


async def send_weekly_digest(c, force: bool = False, team_id=None) -> bool:
    s = c.settings
    if s.digest_weekday < 0 and not force:
        return False
    local_now = c.clock.now().astimezone(s.tz)
    today = c.clock.today()
    if not force and (today.weekday() != s.digest_weekday or local_now.hour < s.digest_hour):
        return False
    channel = c.channels.get("telegram")
    if channel is None or not isinstance(channel, (TelegramChannel, LogTelegramChannel)):
        return False
    any_sent = False
    failed = False
    with c.session_factory() as db:
        teams = TeamRepository(db).list_active(c.clock.now())
        if team_id is not None:
            teams = [t for t in teams if t.id == team_id]
        plans = []
        for team in teams:
            recipient = telegram_recipient(db, team)
            if not recipient:
                continue
            key = digest_key(today, team.id) if not force else f"dm:{uuid.uuid4().hex}"
            claimed = db.execute(
                insert(AppMeta).values(key=key, value="sending").on_conflict_do_nothing().returning(AppMeta.key)
            ).first()
            if not claimed:
                continue
            answer = BotAnswers(db, c.clock, team.id).weekly_digest()
            plans.append((team, recipient, key, answer))
        db.commit()
    if not plans:
        return False
    sent_keys: list[str] = []
    failed_keys: list[str] = []
    for _team, recipient, key, answer in plans:
        ok = True
        if isinstance(channel, TelegramChannel):
            try:
                await channel.client.send_message(recipient, answer.text, answer.reply_markup())
            except Exception as exc:  # noqa: BLE001
                ok = False
                log.warning("Сводка не отправлена в %s: %s", recipient, exc)
        else:
            log.warning("[DRY-RUN Telegram] Сводка на неделю:\n%s", answer.text)
        if ok:
            sent_keys.append(key)
            any_sent = True
        else:
            failed_keys.append(key)
            failed = True
    with c.session_factory() as db:
        for key in sent_keys:
            db.merge(AppMeta(key=key, value=c.clock.now().isoformat()))
        if failed_keys:
            db.execute(delete(AppMeta).where(AppMeta.key.in_(failed_keys)))
        db.commit()
    return any_sent and not failed
