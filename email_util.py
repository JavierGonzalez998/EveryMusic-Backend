import logging
import smtplib
from email.message import EmailMessage

from config import settings

log = logging.getLogger("em-back")


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        # Dev/test: no SMTP — log the message so the link is still recoverable.
        log.info("EMAIL (no SMTP) to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user or "no-reply@em-back"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
