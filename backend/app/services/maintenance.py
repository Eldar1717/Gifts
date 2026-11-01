"""Background maintenance loop: reservations, holds, refund retries."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models import JobLock
from app.services import ledger
from app.services.marketplace import expire_stale_orders, release_expired_reservations

logger = get_logger(__name__)
LOCK_NAME = "maintenance"


def _acquire_lock(db, holder: str, ttl_seconds: int) -> bool:
    now = utcnow()
    row = db.get(JobLock, LOCK_NAME)
    if row and row.locked_until > now:
        return False
    if row is None:
        row = JobLock(name=LOCK_NAME, locked_until=now + timedelta(seconds=ttl_seconds), holder=holder)
        db.add(row)
    else:
        row.locked_until = now + timedelta(seconds=ttl_seconds)
        row.holder = holder
    db.commit()
    return True


def run_once() -> dict[str, int]:
    db = SessionLocal()
    result = {"reservations": 0, "stale_orders": 0, "settled": 0, "refunds": 0}
    try:
        result["reservations"] = release_expired_reservations(db)
        result["stale_orders"] = expire_stale_orders(db)
        result["settled"] = ledger.settle_due_holds(db)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("maintenance.failed")
    finally:
        db.close()
    return result


async def maintenance_loop(stop_event: asyncio.Event) -> None:
    holder = f"worker-{id(stop_event)}"
    logger.info("maintenance.started", extra={"event": f"interval={settings.cleanup_interval_seconds}s"})
    while not stop_event.is_set():
        db = SessionLocal()
        acquired = False
        try:
            acquired = _acquire_lock(db, holder, settings.cleanup_interval_seconds * 3)
        except Exception:
            db.rollback()
            logger.exception("maintenance.lock_failed")
        finally:
            db.close()
        if acquired:
            stats = await asyncio.to_thread(run_once)
            if any(stats.values()):
                logger.info("maintenance.tick", extra={"event": str(stats)})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.cleanup_interval_seconds)
        except asyncio.TimeoutError:
            continue
    logger.info("maintenance.stopped")
