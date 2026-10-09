"""Outgoing email over SMTP. Without SMTP_HOST, messages are only logged (development).

Every email has a plain-text part and an HTML part (one button, right-to-left for Arabic), so
it reads well everywhere and spam filters see a normal message. Test the setup with
`python -m scripts.send_test_email you@example.com`.
"""

import asyncio
import html
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def action_email(
    *,
    title: str,
    intro: str,
    button: str,
    link: str,
    note: str,
    quote: str = "",
    rtl: bool = False,
) -> tuple[str, str]:
    """(plain text, HTML) of a one-button email such as "confirm your email"."""
    text = (
        f"{title}\n\n{intro}\n"
        + (f"\n{quote}\n\n" if quote else "")
        + f"{link}\n\n{note}\n\nReplisto"
    )
    e = html.escape
    direction, align = ("rtl", "right") if rtl else ("ltr", "left")
    quote_html = (
        f'<tr><td style="padding-bottom:20px;"><div style="background:#f1f5f4;border-radius:12px;padding:14px 16px;font-size:15px;line-height:24px;color:#1f2a2c;white-space:pre-wrap;">{e(quote)}</div></td></tr>'
        if quote
        else ""
    )
    page = f"""<!doctype html>
<html dir="{direction}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{e(title)}</title></head>
<body style="margin:0;padding:0;background:#eef4f3;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef4f3;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;padding:32px 28px;text-align:{align};direction:{direction};">
<tr><td style="font-size:22px;font-weight:800;color:#0f766e;padding-bottom:20px;">Replisto</td></tr>
<tr><td style="font-size:19px;font-weight:700;color:#10201f;padding-bottom:12px;">{e(title)}</td></tr>
<tr><td style="font-size:15px;line-height:26px;color:#3b4a4b;padding-bottom:20px;">{e(intro)}</td></tr>
{quote_html}
<tr><td style="padding-bottom:24px;">
<a href="{e(link)}" style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;padding:12px 28px;border-radius:10px;">{e(button)}</a>
</td></tr>
<tr><td style="font-size:13px;line-height:22px;color:#6b7a7b;padding-bottom:8px;">{e(note)}</td></tr>
<tr><td style="font-size:12px;line-height:20px;color:#94a3a3;direction:ltr;text-align:left;word-break:break-all;">{e(link)}</td></tr>
</table>
</td></tr></table>
</body></html>"""
    return text, page


async def send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("email not sent (SMTP_HOST is empty) to %s: %s\n%s", to, subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    domain = settings.smtp_from.rsplit("@", 1)[-1].strip(" >") or None
    message["Message-ID"] = make_msgid(domain=domain)
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    await asyncio.to_thread(_send, message)


def _send(message: EmailMessage) -> None:
    settings = get_settings()
    if settings.smtp_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    with smtp:
        if settings.smtp_starttls and not settings.smtp_ssl:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
