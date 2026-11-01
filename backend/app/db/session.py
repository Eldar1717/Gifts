"""Database engine, session factory and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine_kwargs: dict = {"echo": settings.db_echo, "pool_pre_ping": True, "future": True}
if settings.is_postgres:
    engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=1800,
    )
else:
    # SQLite is supported for local development and the automated test-suite.
    engine_kwargs.update(connect_args={"check_same_thread": False})

engine: Engine = create_engine(settings.database_url, **engine_kwargs)

if not settings.is_postgres:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _record):  # pragma: no cover - driver detail
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for background jobs and scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def lock_row(db: Session, model, *criteria):
    """``SELECT … FOR UPDATE`` on PostgreSQL (a no-op on SQLite).

    Returns a ``ScalarResult`` so call sites can use ``.first()`` / ``.all()``.
    Row locks are what prevents two buyers from taking the same listing in
    production. SQLite (local development and the test-suite) serialises
    writes at the database level instead.
    """
    query = select(model).where(*criteria)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    return db.scalars(query)
