"""Public catalogue endpoints (no Telegram auth required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_optional_user
from app.core.config import settings
from app.core.rate_limit import READ_LIMIT
from app.db.session import get_db
from app.models import Category, Collection, CollectionItem, Order, Review, User
from app.schemas.catalog import (
    CategoryPublic,
    CollectionPublic,
    CollectionItemCard,
    HomeResponse,
    ItemDetail,
    MarketCard,
    MarketplaceConfig,
    ReviewPublic,
)
from app.schemas.common import Page
from app.schemas.users import SellerProfileResponse, StatsPublic, UserShort
from app.schemas.catalog import OwnershipCard
from app.services import catalog as catalog_service
from app.services.platform import get_platform_settings
from app.services.presenters import (
    collection_public,
    item_card,
    market_card_from_listing,
    ownership_card,
    user_short,
)

router = APIRouter(tags=["catalog"], dependencies=[Depends(READ_LIMIT)])


@router.get("/config", response_model=MarketplaceConfig)
def public_config(db: Session = Depends(get_db)) -> MarketplaceConfig:
    platform = get_platform_settings(db)
    return MarketplaceConfig(
        commission_percent=platform.commission_percent,
        seller_share_percent=100 - platform.commission_percent,
        min_listing_price=platform.min_listing_price,
        max_listing_price=platform.max_listing_price,
        hold_hours=platform.hold_hours,
        min_payout_stars=platform.min_payout_stars,
        payout_note=platform.payout_note,
        maintenance_mode=platform.maintenance_mode,
        maintenance_message=platform.maintenance_message,
    )


@router.get("/home", response_model=HomeResponse)
def home(
    user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
) -> HomeResponse:
    return catalog_service.build_home(db, user=user)


@router.get("/categories", response_model=list[CategoryPublic])
def categories(db: Session = Depends(get_db)) -> list[CategoryPublic]:
    rows = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.id)
    ).all()
    return [CategoryPublic.model_validate(row) for row in rows]


@router.get("/collections", response_model=list[CollectionPublic])
def collections(
    rarity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    featured: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[CollectionPublic]:
    stmt = (
        select(Collection)
        .where(Collection.status == "active")
        .options(joinedload(Collection.category))
        .order_by(Collection.is_featured.desc(), Collection.created_at.desc())
        .limit(limit)
    )
    if rarity:
        stmt = stmt.where(Collection.rarity == rarity)
    if category:
        stmt = stmt.where(Collection.category.has(slug=category))
    if featured is not None:
        stmt = stmt.where(Collection.is_featured.is_(featured))
    rows = db.scalars(stmt).unique().all()
    result: list[CollectionPublic] = []
    for collection in rows:
        items_count, sold, floor = catalog_service.collection_stats(db, collection)
        result.append(
            collection_public(collection, items_count=items_count, items_sold=sold, floor=floor)
        )
    return result


@router.get("/collections/{slug}")
def collection_detail(slug: str, db: Session = Depends(get_db)) -> dict:
    collection = db.scalar(
        select(Collection).where(Collection.slug == slug).options(joinedload(Collection.category))
    )
    if collection is None or collection.status == "archived":
        raise HTTPException(404, "Коллекция не найдена")
    items = db.scalars(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection.id)
        .where(CollectionItem.status != "draft")
        .options(joinedload(CollectionItem.collection))
        .order_by(CollectionItem.primary_price_stars.asc())
    ).unique().all()
    items_count, sold, floor = catalog_service.collection_stats(db, collection)
    return {
        "collection": collection_public(
            collection, items_count=items_count, items_sold=sold, floor=floor
        ),
        "items": [item_card(item) for item in items],
    }


@router.get("/items", response_model=Page[CollectionItemCard])
def items(
    q: str | None = Query(default=None, max_length=80),
    collection: str | None = Query(default=None, max_length=80),
    rarity: list[str] | None = Query(default=None),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    sort: str = Query(default="recent"),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=24, ge=1, le=60),
    db: Session = Depends(get_db),
) -> Page[CollectionItemCard]:
    stmt = (
        select(CollectionItem)
        .join(CollectionItem.collection)
        .where(CollectionItem.status.in_(["active", "sold_out"]))
        .where(Collection.status == "active")
        .options(joinedload(CollectionItem.collection))
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(CollectionItem.name.ilike(like) | Collection.name.ilike(like))
    if collection:
        stmt = stmt.where(Collection.slug == collection)
    if rarity:
        stmt = stmt.where(CollectionItem.rarity.in_(rarity))
    if min_price is not None:
        stmt = stmt.where(CollectionItem.primary_price_stars >= min_price)
    if max_price is not None:
        stmt = stmt.where(CollectionItem.primary_price_stars <= max_price)
    if sort == "price_asc":
        stmt = stmt.order_by(CollectionItem.primary_price_stars.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(CollectionItem.primary_price_stars.desc())
    elif sort == "popular":
        stmt = stmt.order_by(CollectionItem.minted_count.desc())
    else:
        stmt = stmt.order_by(CollectionItem.created_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return Page.build([item_card(item) for item in rows], int(total), page, page_size)


def _build_item_detail(db: Session, item: CollectionItem, user: User | None, listing=None) -> ItemDetail:
    active_listing = listing or catalog_service.active_listing_for_item(db, item.id)
    base = (
        catalog_service.market_card_from_listing(active_listing)
        if active_listing
        else catalog_service.market_card_primary(item)
    )
    collection = item.collection
    items_count, sold, floor = catalog_service.collection_stats(db, collection)
    owned_by_me = False
    if user:
        owned_by_me = bool(
            db.scalar(
                select(func.count())
                .select_from(catalog_service.GiftOwnership)
                .where(
                    catalog_service.GiftOwnership.item_id == item.id,
                    catalog_service.GiftOwnership.owner_id == user.id,
                )
            )
        )
    can_buy = False
    if active_listing:
        can_buy = bool(user and active_listing.seller_id != user.id)
    elif item.status == "active" and item.minted_count < item.edition_size:
        can_buy = True
    return ItemDetail(
        **base.model_dump(),
        description=item.description,
        collection=collection_public(
            collection, items_count=items_count, items_sold=sold, floor=floor
        ),
        price_history=catalog_service.price_history(db, item.id),
        recent_sales=catalog_service.sales_history(db, item.id),
        owners_history=catalog_service.owners_history(db, base.ownership_id, item.id),
        favorite=catalog_service.is_favorite(db, user.id if user else None, item.id),
        owned_by_me=owned_by_me,
        can_buy=can_buy,
        remaining=item.remaining,
        edition_size=item.edition_size,
        minted_count=item.minted_count,
    )


@router.get("/items/{item_id}", response_model=ItemDetail)
def item_detail(
    item_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ItemDetail:
    item = db.scalar(
        select(CollectionItem)
        .where(CollectionItem.id == item_id)
        .options(joinedload(CollectionItem.collection))
    )
    if item is None or item.status == "draft":
        raise HTTPException(404, "Подарок не найден")
    return _build_item_detail(db, item, user)


@router.get("/market", response_model=Page[MarketCard])
def market(
    q: str | None = Query(default=None, max_length=80),
    collection: str | None = Query(default=None, max_length=80),
    category: str | None = Query(default=None, max_length=64),
    rarity: list[str] | None = Query(default=None),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    kind: str = Query(default="all", pattern="^(all|primary|resale)$"),
    sort: str = Query(default="recent", pattern="^(recent|price_asc|price_desc|popular|rarity)$"),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=24, ge=1, le=60),
    db: Session = Depends(get_db),
) -> Page[MarketCard]:
    filters = catalog_service.MarketFilters(
        q=q,
        collection=collection,
        category=category,
        rarity=rarity,
        min_price=min_price,
        max_price=max_price,
    )
    cards, total = catalog_service.query_market(
        db, filters, kind=kind, sort=sort, page=page, page_size=page_size
    )
    return Page.build(cards, total, page, page_size)


@router.get("/market/listings/{listing_id}", response_model=ItemDetail)
def listing_detail(
    listing_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ItemDetail:
    from app.models import MarketplaceListing

    listing = db.scalar(
        select(MarketplaceListing)
        .where(MarketplaceListing.id == listing_id)
        .options(
            joinedload(MarketplaceListing.ownership).joinedload(catalog_service.GiftOwnership.item).joinedload(CollectionItem.collection),
            joinedload(MarketplaceListing.seller),
        )
    )
    if listing is None or listing.status in {"cancelled", "expired"}:
        raise HTTPException(404, "Объявление не найдено")
    if listing.status == "active":
        listing.views += 1
        db.commit()
    return _build_item_detail(db, listing.ownership.item, user, listing=listing)


@router.get("/sellers/{user_id}", response_model=SellerProfileResponse)
def seller_profile(user_id: int, db: Session = Depends(get_db)) -> SellerProfileResponse:
    user = db.get(User, user_id)
    if user is None or user.is_blocked:
        raise HTTPException(404, "Продавец не найден")
    listings_count = db.scalar(
        select(func.count())
        .select_from(catalog_service.MarketplaceListing)
        .where(
            catalog_service.MarketplaceListing.seller_id == user.id,
            catalog_service.MarketplaceListing.status == "active",
        )
    ) or 0
    sales = db.scalars(
        select(Order)
        .where(Order.seller_id == user.id, Order.status == "fulfilled")
        .options(joinedload(Order.item))
        .order_by(Order.fulfilled_at.desc())
        .limit(6)
    ).unique().all()
    gross_sales = db.scalar(
        select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
            Order.seller_id == user.id, Order.status == "fulfilled"
        )
    ) or 0
    purchased = db.scalar(
        select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
            Order.buyer_id == user.id, Order.status == "fulfilled"
        )
    ) or 0
    gifts_owned = db.scalar(
        select(func.count())
        .select_from(catalog_service.GiftOwnership)
        .where(
            catalog_service.GiftOwnership.owner_id == user.id,
            catalog_service.GiftOwnership.status == "owned",
        )
    ) or 0
    return SellerProfileResponse(
        user=UserShort(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            photo_url=user.photo_url,
            rating=user.rating,
        ),
        stats=StatsPublic(
            gifts_owned=int(gifts_owned),
            listings_active=int(listings_count),
            sales_count=user.sales_count,
            purchases_count=user.purchases_count,
            gross_sales_stars=int(gross_sales),
            gross_purchases_stars=int(purchased),
            rating_count=user.rating_count,
            rating=user.rating,
        ),
        listings_count=int(listings_count),
        collection_visible=user.show_collection,
        recently_sold=[order.item.name for order in sales],
    )


@router.get("/sellers/{user_id}/listings", response_model=list[MarketCard])
def seller_listings(user_id: int, db: Session = Depends(get_db)) -> list[MarketCard]:
    """Active resale listings of one seller."""
    from app.models import MarketplaceListing

    rows = db.scalars(
        select(MarketplaceListing)
        .where(
            MarketplaceListing.seller_id == user_id,
            MarketplaceListing.status == "active",
        )
        .options(
            joinedload(MarketplaceListing.ownership).joinedload(catalog_service.GiftOwnership.item).joinedload(CollectionItem.collection),
            joinedload(MarketplaceListing.seller),
        )
        .order_by(MarketplaceListing.listed_at.desc())
        .limit(60)
    ).unique().all()
    return [market_card_from_listing(row) for row in rows]


@router.get("/sellers/{user_id}/collection", response_model=list[OwnershipCard])
def seller_collection(user_id: int, db: Session = Depends(get_db)) -> list[OwnershipCard]:
    """Public collection of a seller (only if they enabled it)."""
    user = db.get(User, user_id)
    if user is None or user.is_blocked:
        raise HTTPException(404, "Коллекционер не найден")
    if not user.show_collection:
        raise HTTPException(403, "Коллекционер скрыл свои подарки")
    ownerships = db.scalars(
        select(catalog_service.GiftOwnership)
        .where(
            catalog_service.GiftOwnership.owner_id == user_id,
            catalog_service.GiftOwnership.status == "owned",
        )
        .options(
            joinedload(catalog_service.GiftOwnership.item).joinedload(CollectionItem.collection),
            joinedload(catalog_service.GiftOwnership.owner),
        )
        .order_by(catalog_service.GiftOwnership.acquired_at.desc())
        .limit(60)
    ).unique().all()
    listings = db.scalars(
        select(catalog_service.MarketplaceListing)
        .where(
            catalog_service.MarketplaceListing.ownership_id.in_([row.id for row in ownerships] or [0]),
            catalog_service.MarketplaceListing.status.in_(["active", "reserved"]),
        )
        .options(joinedload(catalog_service.MarketplaceListing.seller))
    ).unique().all()
    listing_map = {row.ownership_id: row for row in listings}
    cards: list[OwnershipCard] = []
    for ownership in ownerships:
        card = ownership_card(ownership, listing_map.get(ownership.id))
        card.estimated_value_stars = (
            catalog_service.cheapest_listing_price(db, ownership.item_id)
            or ownership.item.primary_price_stars
        )
        cards.append(card)
    return cards


@router.get("/sellers/{user_id}/reviews", response_model=Page[ReviewPublic])
def seller_reviews(
    user_id: int,
    page: int = Query(default=1, ge=1, le=200),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> Page[ReviewPublic]:
    base = select(Review).where(Review.seller_id == user_id, Review.is_hidden.is_(False))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(Review.author))
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            ReviewPublic(
                id=row.id,
                rating=row.rating,
                comment=row.comment,
                created_at=row.created_at,
                author=user_short(row.author),
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.get("/meta")
def meta() -> dict:
    """Client bootstrap hints (safe, non-secret)."""
    return {
        "bot_username": settings.bot_username,
        "webapp_url": settings.webapp_url,
        "dev_mode": settings.dev_mode_enabled,
        "bot_configured": settings.bot_configured,
        "ton_enabled": bool(settings.tonapi_base_url),
        "currency": "XTR",
        "app_name": "GIFT MARKET",
    }
