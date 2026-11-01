"""Commission arithmetic. The single source of truth for money splits."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class Split:
    amount_stars: int
    commission_stars: int
    seller_stars: int
    commission_percent: int
    seller_percent: int


def split_amount(amount_stars: int, commission_percent: int) -> Split:
    """Split a sale amount into platform commission and seller income.

    Commission is rounded **down** to a whole Star and the remainder always
    goes to the seller, so ``commission + seller == amount`` holds for every
    input. With the default 10% and a 500 Stars sale: 50 / 450.
    """
    if amount_stars <= 0:
        raise ValueError("amount_stars must be positive")
    if not 0 <= commission_percent <= 50:
        raise ValueError("commission_percent must be between 0 and 50")
    commission = amount_stars * commission_percent // 100
    seller = amount_stars - commission
    return Split(
        amount_stars=amount_stars,
        commission_stars=commission,
        seller_stars=seller,
        commission_percent=commission_percent,
        seller_percent=100 - commission_percent,
    )


def default_commission_percent() -> int:
    return settings.commission_percent
