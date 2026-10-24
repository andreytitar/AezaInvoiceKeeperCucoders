"""Сборка iCalendar (RFC 5545) без внешних библиотек: события на весь день с напоминаниями."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    day: date
    summary: str
    description: str
    alarms: bool = True


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Перенос строк длиннее 75 октетов (RFC 5545, 3.1)."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode())
            cur = b""
        cur += b
    parts.append(cur.decode())
    return "\r\n ".join(parts)


def build_ics(name: str, events: list[CalendarEvent], stamp: datetime, tz: str) -> str:
    ts = stamp.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Invoice Keeper//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        f"X-WR-TIMEZONE:{tz}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for e in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}",
            f"DTSTAMP:{ts}",
            f"DTSTART;VALUE=DATE:{e.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{e.day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(e.summary)}",
            f"DESCRIPTION:{_escape(e.description)}",
            "TRANSP:TRANSPARENT",
        ]
        if e.alarms:
            for trigger, text in (("-P2DT15H", "Через 3 дня оплата"), ("PT9H", "Сегодня оплата")):
                lines += [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_escape(text + ': ' + e.summary)}",
                    f"TRIGGER:{trigger}",
                    "END:VALARM",
                ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
