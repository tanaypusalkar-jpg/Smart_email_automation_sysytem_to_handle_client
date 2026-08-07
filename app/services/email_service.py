"""
Handles actually dispatching email over SMTP.
"""

import logging
from email.mime.text import MIMEText

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger("email_automation.email")

settings = get_settings()


async def send_email(to: str, subject: str, body: str) -> tuple[str, str]:
    """
    Returns (status, detail). status is "dry_run" or "sent".
    Never raises for the dry-run case; raises RuntimeError on real SMTP failure.
    """
    if settings.dry_run:
        logger.info("[DRY RUN] Would send email to %s | subject=%s", to, subject)
        return "dry_run", f"DRY_RUN is on - nothing was sent. Would have gone to {to}."

    if not settings.smtp_username or not settings.smtp_password:
        raise RuntimeError("SMTP_USERNAME/SMTP_PASSWORD are not set in .env.")

    message = MIMEText(body, "plain")
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_username}>"
    message["To"] = to
    message["Subject"] = subject

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )
    except Exception as exc:
        logger.error("SMTP send failed: %s", exc)
        raise RuntimeError(f"SMTP send failed: {exc}") from exc

    logger.info("Email sent to %s", to)
    return "sent", f"Email sent to {to}."
