"""
Database engine and session handling.

SQLite by default (zero setup, one file, fine for a portfolio project).
Point DATABASE_URL at Postgres in production and nothing else in this
file needs to change - that's the entire reason to go through SQLAlchemy
instead of writing raw sqlite3 calls.
"""

from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings

settings = get_settings()

# check_same_thread=False is only needed for SQLite (FastAPI can call from
# different threads); it's a no-op / ignored for other DB backends.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    """FastAPI dependency - yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist yet. Called once at startup."""
    from app import models_db  # noqa: F401 - import registers the model with Base

    Base.metadata.create_all(bind=engine)
