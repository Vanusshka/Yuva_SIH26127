"""
Database setup for SIH26127 ANPR backend.

Engine / Session / Base are created here.
All ORM models import Base from this module.

To switch from SQLite → PostgreSQL:
  Change DATABASE_URL in config.py only.
  No other code needs to change.
"""

from __future__ import annotations
import logging
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── Declarative base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── SQLite column migration helper ────────────────────────────────────────────
def _add_column_if_missing(conn, table: str, column: str, col_def: str) -> None:
    """
    Add a column to a SQLite table if it does not already exist.
    Uses PRAGMA table_info which is available in all SQLite versions.
    """
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result}
    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
        logger.info("[DB Migration] Added column %s.%s", table, column)


def _migrate_v2(conn) -> None:
    """
    Change 4 — Add OCR evidence and category fields to vehicle_events.
    Safe to run on every startup: skips columns that already exist.
    """
    migrations = [
        # (column_name, SQLite type definition)
        ("confidence_tier",     "TEXT"),
        ("valid_ocr_reads",     "INTEGER"),
        ("matching_ocr_reads",  "INTEGER"),
        ("agreement_rate",      "REAL"),
        ("vehicle_category",    "TEXT"),
    ]
    for col, typedef in migrations:
        try:
            _add_column_if_missing(conn, "vehicle_events", col, typedef)
        except Exception as exc:
            logger.warning("[DB Migration] vehicle_events.%s: %s", col, exc)


# ── Table creation ────────────────────────────────────────────────────────────
def init_db() -> None:
    """
    Create all tables that don't already exist and run column migrations.
    Safe to call on every startup.
    """
    import app.models.camera              # noqa: F401
    import app.models.vehicle_event       # noqa: F401
    import app.models.trajectory_camera   # noqa: F401
    import app.models.detection           # noqa: F401
    import app.models.manual_review       # noqa: F401  Change 6

    Base.metadata.create_all(bind=engine)

    # Run column migrations for existing tables
    with engine.begin() as conn:
        _migrate_v2(conn)


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
