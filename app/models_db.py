"""
ORM models. Just one table for now: a flat audit log of everything the
system classified, drafted, or sent. Deliberately not normalized into
separate "emails" / "classifications" tables - at this scale that split
adds joins without adding value. Revisit if this grows real query needs.
"""

from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[str] = mapped_column(String(10))       # "incoming" | "outgoing"
    action: Mapped[str] = mapped_column(String(20))          # "classify" | "compose" | "reply" | "send"
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20))          # "drafted" | "sent" | "dry_run" | "error"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
