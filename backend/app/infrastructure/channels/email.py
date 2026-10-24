"""Email-канал через SMTP (smtplib в отдельном потоке). Тот же механизм доставки: UNIQUE, ретраи, без дублей."""

from __future__ import annotations

import asyncio
import html
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import make_msgid

from app.config import Settings
from app.domain.money import NBSP, format_amount
from app.infrastructure.channels.base import Notification, SendResult
from app.infrastructure.channels.formatting import due_phrase, plain_text


def build_email(n: Notification, sender: str, recipient: str) -> EmailMessage:
    msg = EmailMessage()
    prefix = "Просрочен платёж" if n.days_until_due < 0 else "Напоминание об оплате"
    msg["Subject"] = f"{prefix}: {n.title} — {n.due_date:%d.%m.%Y}"
    msg["From"] = sender
    msg["To"] = recipient
    msg["Message-ID"] = make_msgid(idstring=f"{n.occurrence_id}.{n.kind}")
    msg["X-Invoice-Keeper-Occurrence"] = str(n.occurrence_id)
    msg.set_content(plain_text(n) + "\n\n— Invoice Keeper")
    amount = html.escape(format_amount(n.amount, n.currency))
    msg.add_alternative(
        f"""<div style="font-family:Georgia,serif;color:#1d1b17;background:#f4efe4;padding:24px">
<h2 style="margin:0 0 12px">{html.escape(prefix)}</h2>
<table style="border-collapse:collapse;font-family:Menlo,monospace;font-size:14px">
<tr><td style="padding:4px 16px 4px 0;color:#5d574c">Название</td><td><b>{html.escape(n.title)}</b></td></tr>
<tr><td style="padding:4px 16px 4px 0;color:#5d574c">Сумма</td><td><b>{amount}</b>{NBSP}({n.currency})</td></tr>
<tr><td style="padding:4px 16px 4px 0;color:#5d574c">Дата оплаты</td><td><b>{n.due_date:%d.%m.%Y}</b> — {html.escape(due_phrase(n.days_until_due))}</td></tr>
</table></div>""",
        subtype="html",
    )
    return msg


SmtpFactory = Callable[[Settings], smtplib.SMTP]


def default_smtp_factory(s: Settings) -> smtplib.SMTP:
    if s.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            s.smtp_host or "", s.smtp_port, timeout=s.smtp_timeout_seconds, context=ssl.create_default_context()
        )
    else:
        client = smtplib.SMTP(s.smtp_host or "", s.smtp_port, timeout=s.smtp_timeout_seconds)
        if s.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
    if s.smtp_user:
        client.login(s.smtp_user, s.smtp_password or "")
    return client


class EmailChannel:
    name = "email"

    def __init__(
        self,
        settings: Settings,
        user_emails: Callable[[], list[str]] | None = None,
        smtp_factory: SmtpFactory = default_smtp_factory,
    ) -> None:
        self.settings = settings
        self.user_emails = user_emails
        self.smtp_factory = smtp_factory

    def recipients(self) -> list[str]:
        result = list(self.settings.email_static_recipients)
        if self.settings.email_to_users and self.user_emails:
            result += self.user_emails()
        seen: set[str] = set()
        return [r for r in result if not (r.lower() in seen or seen.add(r.lower()))]

    def _send_sync(self, message: Notification, recipient: str) -> None:
        msg = build_email(message, self.settings.smtp_from, recipient)
        client = self.smtp_factory(self.settings)
        try:
            client.send_message(msg)
        finally:
            try:
                client.quit()
            except Exception:  # noqa: BLE001
                pass

    async def send(self, message: Notification, recipient: str) -> SendResult:
        try:
            await asyncio.to_thread(self._send_sync, message, recipient)
        except smtplib.SMTPRecipientsRefused as exc:
            return SendResult(ok=False, error=f"SMTP: получатель отклонён {list(exc.recipients)}", retryable=False)
        except (smtplib.SMTPException, OSError) as exc:
            return SendResult(ok=False, error=f"SMTP: {type(exc).__name__}: {exc}")
        return SendResult(ok=True)
