"""SQLAlchemy engine, session factory, and declarative base."""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def utcnow() -> datetime:
    """Return the current UTC timestamp with timezone info.

    This is the project's canonical timestamp helper – all Python-side
    timestamps should use this instead of calling datetime.now() directly.
    """
    return datetime.now(timezone.utc)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.debug,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Shared declarative base for all SFR models."""


def get_session():
    """Yield a synchronous session – used by FastAPI dependency injection."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_session() -> AsyncGenerator:
    """Async-compatible generator wrapping the sync session (for use with async routes)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
