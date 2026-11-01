"""Minting and transferring collectibles with a full ownership trail."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AcquisitionType, GiftStatus, OwnershipEvent, OwnershipStatus
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import lock_row
from app.models import CollectionItem, GiftOwnership, Order, OwnershipHistory, User

logger = get_logger(__name__)


class OwnershipError(Exception):
    pass


def mint_primary(
    db: Session, *, item: CollectionItem, buyer: User, order: Order
) -> GiftOwnership:
    """Create a new serialized instance for a primary (first) sale.

    The item row must already be locked by the caller. Serial numbers are
    allocated from ``minted_count`` which guarantees uniqueness inside the
    transaction and is backed by a database unique constraint.
    """
    if item.status != GiftStatus.ACTIVE.value:
        raise OwnershipError("Подарок недоступен к продаже")
    if item.minted_count >= item.edition_size:
        raise OwnershipError("Тираж распродан")

    serial = item.minted_count + 1 if item.is_serialized else None
    ownership = GiftOwnership(
        item_id=item.id,
        owner_id=buyer.id,
        serial_number=serial,
        status=OwnershipStatus.OWNED.value,
        acquisition_type=AcquisitionType.PRIMARY.value,
        acquired_price_stars=order.amount_stars,
        acquired_at=utcnow(),
    )
    db.add(ownership)
    db.flush()

    item.minted_count += 1
    if item.minted_count >= item.edition_size:
        item.status = GiftStatus.SOLD_OUT.value

    db.add(
        OwnershipHistory(
            ownership_id=ownership.id,
            from_user_id=None,
            to_user_id=buyer.id,
            order_id=order.id,
            event=OwnershipEvent.MINT.value,
            price_stars=order.amount_stars,
        )
    )
    buyer.purchases_count += 1
    logger.info(
        "ownership.minted",
        extra={"user_id": buyer.id, "order_id": order.id, "event": f"serial={serial}"},
    )
    return ownership


def transfer_resale(
    db: Session, *, ownership: GiftOwnership, order: Order
) -> GiftOwnership:
    """Transfer an existing instance from the seller to the buyer."""
    if ownership.owner_id != order.seller_id:
        raise OwnershipError("Владелец предмета изменился")
    if ownership.status != OwnershipStatus.OWNED.value:
        raise OwnershipError("Предмет недоступен")

    previous_owner_id = ownership.owner_id
    ownership.owner_id = order.buyer_id
    ownership.acquired_at = utcnow()
    ownership.acquired_price_stars = order.amount_stars
    ownership.acquisition_type = AcquisitionType.RESALE.value

    db.add(
        OwnershipHistory(
            ownership_id=ownership.id,
            from_user_id=previous_owner_id,
            to_user_id=order.buyer_id,
            order_id=order.id,
            event=OwnershipEvent.RESALE.value,
            price_stars=order.amount_stars,
        )
    )
    buyer = db.get(User, order.buyer_id)
    seller = db.get(User, order.seller_id) if order.seller_id else None
    if buyer:
        buyer.purchases_count += 1
    if seller:
        seller.sales_count += 1
    logger.info("ownership.transferred", extra={"order_id": order.id, "user_id": order.buyer_id})
    return ownership


def grant_item(db: Session, *, item: CollectionItem, user: User, price: int, admin_id: int) -> GiftOwnership:
    """Admin grant: mint an instance directly to a user."""
    item_locked = lock_row(db, CollectionItem, CollectionItem.id == item.id).first()
    if item_locked is None:
        raise OwnershipError("Подарок не найден")
    if item_locked.minted_count >= item_locked.edition_size:
        raise OwnershipError("Тираж распродан")
    serial = item_locked.minted_count + 1 if item_locked.is_serialized else None
    ownership = GiftOwnership(
        item_id=item_locked.id,
        owner_id=user.id,
        serial_number=serial,
        status=OwnershipStatus.OWNED.value,
        acquisition_type=AcquisitionType.ADMIN_GRANT.value,
        acquired_price_stars=price,
    )
    db.add(ownership)
    db.flush()
    item_locked.minted_count += 1
    if item_locked.minted_count >= item_locked.edition_size:
        item_locked.status = GiftStatus.SOLD_OUT.value
    db.add(
        OwnershipHistory(
            ownership_id=ownership.id,
            from_user_id=None,
            to_user_id=user.id,
            event=OwnershipEvent.ADMIN_GRANT.value,
            price_stars=price,
        )
    )
    logger.info("ownership.admin_grant", extra={"user_id": user.id, "event": f"admin={admin_id}"})
    return ownership


def history_for_ownership(db: Session, ownership_id: int) -> list[OwnershipHistory]:
    return list(
        db.scalars(
            select(OwnershipHistory)
            .where(OwnershipHistory.ownership_id == ownership_id)
            .order_by(OwnershipHistory.created_at.asc(), OwnershipHistory.id.asc())
        ).all()
    )
