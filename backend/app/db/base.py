"""Declarative base and shared column helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp used consistently across PostgreSQL and SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def ensure_aware(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to values read back from the database."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


def iso(value: datetime | None) -> str | None:
    aware = ensure_aware(value)
    return aware.isoformat().replace("+00:00", "Z") if aware else None
