"""Listing lifecycle: create, reprice, cancel, reserve and release."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    ListingStatus,
    OrderStatus,
    OwnershipStatus,
    PriceEvent,
    PriceHistoryScope,
)
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import lock_row
from app.models import GiftOwnership, MarketplaceListing, Order, PriceHistory, User
from app.services.platform import get_platform_settings
from app.services.pricing import split_amount

logger = get_logger(__name__)


class ListingError(Exception):
    pass


def _active_listing_for(db: Session, ownership_id: int) -> MarketplaceListing | None:
    return db.scalar(
        select(MarketplaceListing).where(
            MarketplaceListing.ownership_id == ownership_id,
            MarketplaceListing.status.in_(
                [ListingStatus.ACTIVE.value, ListingStatus.RESERVED.value]
            ),
        )
    )


def create_listing(
    db: Session, *, user: User, ownership_id: int, price_stars: int
) -> MarketplaceListing:
    platform = get_platform_settings(db)
    if platform.maintenance_mode:
        raise ListingError("Маркетплейс временно на техническом обслуживании")
    if price_stars < platform.min_listing_price:
        raise ListingError(f"Минимальная цена — {platform.min_listing_price} Stars")
    if price_stars > platform.max_listing_price:
        raise ListingError(f"Максимальная цена — {platform.max_listing_price} Stars")

    active_count = db.scalar(
        select(func.count(MarketplaceListing.id)).where(
            MarketplaceListing.seller_id == user.id,
            MarketplaceListing.status == ListingStatus.ACTIVE.value,
        )
    )
    if active_count and active_count >= platform.max_active_listings:
        raise ListingError(f"Достигнут лимит активных объявлений ({platform.max_active_listings})")

    ownership = lock_row(db, GiftOwnership, GiftOwnership.id == ownership_id).first()
    if ownership is None or ownership.owner_id != user.id:
        raise ListingError("Предмет не найден в вашей коллекции")
    if ownership.status != OwnershipStatus.OWNED.value:
        raise ListingError("Предмет недоступен для продажи")
    item = ownership.item
    if item.status not in {"active", "sold_out"}:
        raise ListingError("Подарок недоступен для продажи")
    if not item.is_tradeable:
        raise ListingError("Этот подарок нельзя перепродать")

    existing = _active_listing_for(db, ownership.id)
    if existing:
        if existing.status == ListingStatus.ACTIVE.value:
            raise ListingError("Предмет уже выставлен на продажу")
        raise ListingError("Предмет уже забронирован покупателем")

    listing = MarketplaceListing(
        ownership_id=ownership.id,
        seller_id=user.id,
        price_stars=price_stars,
        status=ListingStatus.ACTIVE.value,
        listed_at=utcnow(),
    )
    db.add(listing)
    db.flush()
    db.add(
        PriceHistory(
            item_id=item.id,
            ownership_id=ownership.id,
            listing_id=listing.id,
            scope=PriceHistoryScope.GIFT.value,
            event=PriceEvent.LISTED.value,
            price_stars=price_stars,
        )
    )
    logger.info("listing.created", extra={"user_id": user.id, "event": f"listing={listing.id}"})
    return listing


def update_listing(
    db: Session, *, user: User, listing_id: int, price_stars: int
) -> MarketplaceListing:
    platform = get_platform_settings(db)
    if price_stars < platform.min_listing_price or price_stars > platform.max_listing_price:
        raise ListingError(
            f"Цена должна быть от {platform.min_listing_price} до {platform.max_listing_price} Stars"
        )
    listing = lock_row(db, MarketplaceListing, MarketplaceListing.id == listing_id).first()
    if listing is None or listing.seller_id != user.id:
        raise ListingError("Объявление не найдено")
    if listing.status != ListingStatus.ACTIVE.value:
        raise ListingError("Изменить цену можно только у активного объявления")
    if listing.price_stars == price_stars:
        return listing
    listing.price_stars = price_stars
    db.add(
        PriceHistory(
            item_id=listing.ownership.item_id,
            ownership_id=listing.ownership_id,
            listing_id=listing.id,
            scope=PriceHistoryScope.GIFT.value,
            event=PriceEvent.PRICE_CHANGED.value,
            price_stars=price_stars,
        )
    )
    return listing


def cancel_listing(db: Session, *, user: User, listing_id: int) -> MarketplaceListing:
    listing = lock_row(db, MarketplaceListing, MarketplaceListing.id == listing_id).first()
    if listing is None or listing.seller_id != user.id:
        raise ListingError("Объявление не найдено")
    if listing.status == ListingStatus.RESERVED.value:
        raise ListingError("Покупатель уже оформляет заказ, попробуйте позже")
    if listing.status != ListingStatus.ACTIVE.value:
        raise ListingError("Объявление уже неактивно")
    listing.status = ListingStatus.CANCELLED.value
    listing.cancelled_at = utcnow()
    db.add(
        PriceHistory(
            item_id=listing.ownership.item_id,
            ownership_id=listing.ownership_id,
            listing_id=listing.id,
            scope=PriceHistoryScope.GIFT.value,
            event=PriceEvent.CANCELLED.value,
            price_stars=listing.price_stars,
        )
    )
    return listing


def release_expired_reservations(db: Session) -> int:
    """Release listings whose checkout window expired."""
    now = utcnow()
    expired = db.scalars(
        select(MarketplaceListing).where(
            MarketplaceListing.status == ListingStatus.RESERVED.value,
            MarketplaceListing.reserved_until.is_not(None),
            MarketplaceListing.reserved_until <= now,
        )
    ).all()
    if not expired:
        return 0
    for listing in expired:
        if listing.reserved_order_id:
            order = db.get(Order, listing.reserved_order_id)
            if order and order.status == OrderStatus.PENDING_PAYMENT.value:
                order.status = OrderStatus.EXPIRED.value
                order.failure_reason = "Истекло время оплаты"
        listing.status = ListingStatus.ACTIVE.value
        listing.reserved_order_id = None
        listing.reserved_until = None
    logger.info("listing.reservations_released", extra={"event": f"count={len(expired)}"})
    return len(expired)


def expire_stale_orders(db: Session, *, minutes: int = 30) -> int:
    """Fail pending orders whose invoice window has passed (primary sales)."""
    cutoff = utcnow() - timedelta(minutes=minutes)
    orders = db.scalars(
        select(Order).where(
            Order.status == OrderStatus.PENDING_PAYMENT.value,
            Order.created_at <= cutoff,
        )
    ).all()
    for order in orders:
        order.status = OrderStatus.EXPIRED.value
        order.failure_reason = "Истекло время оплаты"
    return len(orders)


def reserve_listing(db: Session, listing: MarketplaceListing, order: Order, minutes: int) -> None:
    listing.status = ListingStatus.RESERVED.value
    listing.reserved_order_id = order.id
    listing.reserved_until = utcnow() + timedelta(minutes=minutes)


def reprice_preview(platform_percent: int, price: int) -> dict:
    split = split_amount(price, platform_percent)
    return {
        "price_stars": price,
        "commission_stars": split.commission_stars,
        "seller_receives_stars": split.seller_stars,
    }
