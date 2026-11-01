"""ORM -> API model mapping helpers (kept in one place for consistency)."""

from __future__ import annotations

from app.core.enums import ListingStatus
from app.models import (
    CollectionItem,
    GiftOwnership,
    MarketplaceListing,
    Order,
    User,
)
from app.schemas.catalog import (
    CollectionItemCard,
    CollectionPublic,
    CollectionShort,
    ListingPublic,
    MarketCard,
    OwnershipCard,
    OwnershipShort,
    PricePoint,
)
from app.schemas.orders import OrderDetail, OrderPublic, PaymentPublic
from app.schemas.users import UserPublic, UserShort


def user_short(user: User | None) -> UserShort | None:
    if user is None:
        return None
    return UserShort(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        photo_url=user.photo_url,
        rating=user.rating,
    )


def user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        photo_url=user.photo_url,
        display_name=user.display_name,
        rating=user.rating,
        sales_count=user.sales_count,
        purchases_count=user.purchases_count,
        created_at=user.created_at,
    )


def collection_short(collection) -> CollectionShort:
    return CollectionShort(
        id=collection.id,
        slug=collection.slug,
        name=collection.name,
        rarity=collection.rarity,
        cover_url=collection.cover_url,
        accent=collection.accent,
    )


def collection_public(collection, *, items_count: int = 0, items_sold: int = 0, floor: int | None = None) -> CollectionPublic:
    return CollectionPublic(
        id=collection.id,
        slug=collection.slug,
        name=collection.name,
        rarity=collection.rarity,
        cover_url=collection.cover_url,
        accent=collection.accent,
        description=collection.description,
        status=collection.status,
        is_featured=collection.is_featured,
        released_at=collection.released_at,
        category=collection.category,
        ton_collection_address=collection.ton_collection_address,
        chain_verified=collection.chain_verified,
        items_count=items_count,
        items_sold=items_sold,
        floor_price_stars=floor,
    )


def item_card(item: CollectionItem) -> CollectionItemCard:
    return CollectionItemCard(
        id=item.id,
        name=item.name,
        image_url=item.image_url,
        back_image_url=item.back_image_url,
        rarity=item.rarity,
        glow=item.glow,
        primary_price_stars=item.primary_price_stars,
        edition_size=item.edition_size,
        minted_count=item.minted_count,
        remaining=item.remaining,
        status=item.status,
        source=item.source,
        is_tradeable=item.is_tradeable,
        is_featured=item.is_featured,
        collection=collection_short(item.collection),
        created_at=item.created_at,
    )


def market_card_from_listing(listing: MarketplaceListing) -> MarketCard:
    ownership = listing.ownership
    return MarketCard(
        kind="resale",
        key=f"listing-{listing.id}",
        item=item_card(ownership.item),
        listing_id=listing.id,
        ownership_id=ownership.id,
        price_stars=listing.price_stars,
        seller=user_short(listing.seller),
        serial_number=ownership.serial_number,
        listed_at=listing.listed_at,
        views=listing.views,
    )


def market_card_primary(item: CollectionItem) -> MarketCard:
    return MarketCard(
        kind="primary",
        key=f"item-{item.id}",
        item=item_card(item),
        price_stars=item.primary_price_stars,
        listed_at=item.created_at,
    )


def price_point(event: str, price: int, created_at, listing_id: int | None = None) -> PricePoint:
    return PricePoint(
        price_stars=price, event=event, created_at=created_at, listing_id=listing_id
    )


def ownership_short(ownership: GiftOwnership) -> OwnershipShort:
    return OwnershipShort(
        id=ownership.id,
        serial_number=ownership.serial_number,
        owner=user_short(ownership.owner),
        acquired_at=ownership.acquired_at,
        acquired_price_stars=ownership.acquired_price_stars,
    )


def listing_public(listing: MarketplaceListing) -> ListingPublic:
    return ListingPublic(
        id=listing.id,
        price_stars=listing.price_stars,
        status=listing.status,
        listed_at=listing.listed_at,
        reserved_until=listing.reserved_until,
        views=listing.views,
        seller=user_short(listing.seller),
        ownership=ownership_short(listing.ownership),
        item=item_card(listing.ownership.item),
    )


def ownership_card(ownership: GiftOwnership, listing: MarketplaceListing | None = None) -> OwnershipCard:
    active = listing if listing and listing.status in {ListingStatus.ACTIVE.value, ListingStatus.RESERVED.value} else None
    return OwnershipCard(
        id=ownership.id,
        serial_number=ownership.serial_number,
        acquired_at=ownership.acquired_at,
        acquired_price_stars=ownership.acquired_price_stars,
        acquisition_type=ownership.acquisition_type,
        status=ownership.status,
        item=item_card(ownership.item),
        listing=(
            {
                "id": active.id,
                "price_stars": active.price_stars,
                "status": active.status,
                "listed_at": active.listed_at,
                "seller": user_short(active.seller),
            }
            if active
            else None
        ),
        can_list=ownership.status == "owned" and ownership.item.status == "active" and ownership.item.is_tradeable and not active,
    )


def order_public(order: Order, *, reviewed: bool = False) -> OrderPublic:
    return OrderPublic(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        order_type=order.order_type,
        amount_stars=order.amount_stars,
        commission_stars=order.commission_stars,
        seller_amount_stars=order.seller_amount_stars,
        currency=order.currency,
        created_at=order.created_at,
        paid_at=order.paid_at,
        fulfilled_at=order.fulfilled_at,
        item=item_card(order.item),
        seller=user_short(order.seller),
        buyer=user_short(order.buyer),
        serial_number=order.ownership.serial_number if order.ownership else None,
        reviewed=reviewed,
        can_review=order.status == "fulfilled" and not reviewed,
        failure_reason=order.failure_reason,
    )


def order_detail(order: Order, *, reviewed: bool = False) -> OrderDetail:
    base = order_public(order, reviewed=reviewed)
    payment = order.payment
    return OrderDetail(
        **base.model_dump(),
        payment=(
            PaymentPublic(
                id=payment.id,
                status=payment.status,
                amount_stars=payment.amount_stars,
                currency=payment.currency,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                provider_payment_charge_id=payment.provider_payment_charge_id,
                paid_at=payment.paid_at,
                created_at=payment.created_at,
            )
            if payment
            else None
        ),
    )
