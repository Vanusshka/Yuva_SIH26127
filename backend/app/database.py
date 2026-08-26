"""
Database setup for SIH26127 ANPR backend.

Engine / Session / Base are created here.
All ORM models import Base from this module.

To switch from SQLite → PostgreSQL:
  Change DATABASE_URL in config.py only.
  No other code needs to change.
"""

from __future__ import annotations
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import DATABASE_URL


# ── Engine ────────────────────────────────────────────────────────────────────
# connect_args is SQLite-specific; ignored by PostgreSQL
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,          # set True to log SQL statements for debugging
)

# Enable WAL mode for SQLite (better concurrent read performance)
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


# ── Table creation ────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables that don't already exist. Safe to call on every startup."""
    # Import models so SQLAlchemy registers them against Base
    import app.models.camera              # noqa: F401
    import app.models.vehicle_event       # noqa: F401
    import app.models.trajectory_camera   # noqa: F401
    import app.models.detection           # noqa: F401
    Base.metadata.create_all(bind=engine)


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session for the lifetime of a single request.
    Always closed in the finally block.

    Usage in route:
        def my_route(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
