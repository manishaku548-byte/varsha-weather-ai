"""SQLAlchemy engine/session setup (SQLite for the MVP).

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def init_db() -> None:
    """Create tables (audit/override storage). Safe to call repeatedly."""
    from . import models  # noqa: F401  (import registers tables on Base)

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_status() -> str:
    """Return 'connected' or 'error' without ever raising."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "connected"
    except Exception:  # pragma: no cover - only hit on broken local setup
        return "error"
