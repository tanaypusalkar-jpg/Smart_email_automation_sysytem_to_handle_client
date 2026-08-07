"""
Thin helper for writing audit log rows. Kept separate so routers call one
function instead of importing SQLAlchemy models directly - if the logging
strategy changes later (e.g. move to a queue), only this file changes.
"""

import logging
from sqlalchemy.orm import Session

from app.models_db import EmailLog

logger = logging.getLogger("email_automation.log_service")


def record(
    db: Session,
    *,
    direction: str,
    action: str,
    subject: str,
    body: str,
    status: str,
    category: str | None = None,
    priority: str | None = None,
) -> None:
    try:
        entry = EmailLog(
            direction=direction,
            action=action,
            subject=subject[:500],
            body=body,
            category=category,
            priority=priority,
            status=status,
        )
        db.add(entry)
        db.commit()
    except Exception:
        # Logging failures should never break the actual email operation.
        db.rollback()
        logger.exception("Failed to write audit log entry (action=%s)", action)
