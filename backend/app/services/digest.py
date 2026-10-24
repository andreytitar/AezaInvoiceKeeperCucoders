"""Еженедельная сводка в чат напоминаний: просрочено + ближайшие 7 дней.

Раз в неделю (DIGEST_WEEKDAY, DIGEST_HOUR в APP_TIMEZONE). Отправка ровно одна: ключ недели
в app_meta захватывается до отправки (INSERT ... ON CONFLICT DO NOTHING) и снимается, если отправка не удалась.
"""

from __future__ import annotations

import logging
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.channels.telegram import TelegramChannel
from app.models import AppMeta
from app.services.bot_answers import BotAnswers

log = logging.getLogger("app.digest")


def digest_key(today) -> str:
    year, week, _ = today.isocalendar()
    return f"digest:{year}-W{week:02d}"


async def send_weekly_digest(c, force: bool = False) -> bool:
    s = c.settings
    if s.digest_weekday < 0 and not force:
        return False
    local_now = c.clock.now().astimezone(s.tz)
    today = c.clock.today()
    if not force and (today.weekday() != s.digest_weekday or local_now.hour < s.digest_hour):
        return False
    channel = c.channels.get("telegram")
    recipients = channel.recipients() if channel else []
    if not recipients:
        return False
    key = digest_key(today) if not force else f"digest:manual:{c.clock.now().isoformat()}"
    with c.session_factory() as db:
        claimed = db.execute(
            insert(AppMeta).values(key=key, value="sending").on_conflict_do_nothing().returning(AppMeta.key)
        ).first()
        db.commit()
        if not claimed:
            return False
        answer = BotAnswers(db, c.clock).weekly_digest()
    ok = True
    for chat in recipients:
        if isinstance(channel, TelegramChannel):
            try:
                await channel.client.send_message(chat, answer.text, answer.reply_markup())
            except Exception as exc:  # noqa: BLE001
                ok = False
                log.warning("Сводка не отправлена в %s: %s", chat, exc)
        else:
            log.warning("[DRY-RUN Telegram] Сводка на неделю:\n%s", answer.text)
    with c.session_factory() as db:
        if ok:
            db.merge(AppMeta(key=key, value=c.clock.now().isoformat()))
        else:
            db.execute(delete(AppMeta).where(AppMeta.key == key))  # повторим на следующем тике
        db.commit()
    return ok

