"""Runtime platform settings (commission, limits, payout policy)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings as env_settings
from app.models import PlatformSettings


def get_platform_settings(db: Session, *, create: bool = True) -> PlatformSettings:
    row = db.get(PlatformSettings, 1)
    if row is None and create:
        row = PlatformSettings(
            id=1,
            commission_percent=env_settings.commission_percent,
            min_listing_price=env_settings.min_listing_price,
            max_listing_price=env_settings.max_listing_price,
            hold_hours=env_settings.balance_hold_hours,
            min_payout_stars=100,
            payout_note=(
                "Внутренний баланс — не кошелёк. Выплаты выполняются вручную после "
                "проверки и согласования."
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    if row is None:  # pragma: no cover - defensive
        raise RuntimeError("Platform settings row is missing")
    return row


def get_commission_percent(db: Session) -> int:
    return get_platform_settings(db).commission_percent
