"""Bring the database schema up to date when the app starts.

The live service's start command can't be checked (it lives in a Render
account we can't see), so the app doesn't rely on `alembic upgrade head`
having run first. On startup it creates missing tables and adds missing
columns. Every statement is idempotent and only adds; nothing is dropped or
changed, so it is safe to run on every start and in every worker.

Keep this in step with the Alembic migrations: when a migration adds a
column to an existing table, add it to NEW_COLUMNS too.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import Base

logger = logging.getLogger(__name__)

# Columns added to existing tables after they were first created.
# (table, column, SQL type) – migration 0004.
NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("frameworks", "licence_name", "VARCHAR(255)"),
    ("frameworks", "licence_url", "VARCHAR(500)"),
    ("frameworks", "attribution", "TEXT"),
]


# Arbitrary fixed key for pg_advisory_xact_lock: serialises ensure_schema
# across gunicorn workers (and old/new instances) starting at the same time.
_SCHEMA_LOCK_KEY = 72_041_113


def add_column_statements(dialect: str, existing: dict[str, set[str]]) -> list[str]:
    """SQL to add the columns missing from ``existing`` ({table: {column, ...}}).

    Columns already present get no statement, so a normal start doesn't take
    an exclusive lock on the table. PostgreSQL also gets `IF NOT EXISTS` as a
    second guard.
    """
    guard = " IF NOT EXISTS" if dialect == "postgresql" else ""
    return [
        f"ALTER TABLE {table} ADD COLUMN{guard} {column} {sql_type}"
        for table, column, sql_type in NEW_COLUMNS
        if column not in existing.get(table, set())
    ]


def ensure_schema(engine: Engine) -> None:
    """Create missing tables and add missing columns. Raises if the database refuses.

    Runs in one transaction. On PostgreSQL it first takes a transaction-level
    advisory lock, so workers starting together run this one at a time and
    later ones see the tables and columns the first one created.
    """
    import app.models  # noqa: F401  – register every model on Base.metadata

    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SCHEMA_LOCK_KEY})
        Base.metadata.create_all(bind=conn)
        inspector = inspect(conn)
        existing = {
            table: {c["name"] for c in inspector.get_columns(table)}
            for table in {t for t, _, _ in NEW_COLUMNS}
            if inspector.has_table(table)
        }
        statements = add_column_statements(conn.dialect.name, existing)
        for sql in statements:
            conn.execute(text(sql))
    if statements:
        logger.info("Schema check: %d column(s) added", len(statements))
