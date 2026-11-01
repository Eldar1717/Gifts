"""Read-side catalogue queries shared by public routes and the admin panel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import ListingStatus, OrderStatus, PriceEvent, Rarity
from app.db.base import utcnow
from app.models import (
    Collection,
    CollectionItem,
    Favorite,
    GiftOwnership,
    MarketplaceListing,
    Order,
    OwnershipHistory,
    PriceHistory,
    User,
)
from app.schemas.catalog import HomeResponse, HomeStats, MarketCard, RecentSale
from app.services.presenters import (
    collection_public,
    item_card,
    market_card_from_listing,
    market_card_primary,
    price_point,
    user_short,
)

RARITY_ORDER = case(
    {
        Rarity.COMMON.value: 1,
        Rarity.UNCOMMON.value: 2,
        Rarity.RARE.value: 3,
        Rarity.EPIC.value: 4,
        Rarity.LEGENDARY.value: 5,
    },
    value=CollectionItem.rarity,
    else_=0,
)


@dataclass
class MarketFilters:
    q: str | None = None
    collection: str | None = None
    category: str | None = None
    rarity: list[str] | None = None
    min_price: int | None = None
    max_price: int | None = None


def _apply_item_filters(stmt: Select, filters: MarketFilters) -> Select:
    stmt = stmt.join(CollectionItem.collection)
    if filters.q:
        like = f"%{filters.q.strip()}%"
        stmt = stmt.where(
            or_(CollectionItem.name.ilike(like), Collection.name.ilike(like))
        )
    if filters.collection:
        stmt = stmt.where(Collection.slug == filters.collection)
    if filters.category:
        stmt = stmt.where(Collection.category.has(slug=filters.category))
    if filters.rarity:
        stmt = stmt.where(CollectionItem.rarity.in_(filters.rarity))
    return stmt


def _listing_base(filters: MarketFilters) -> Select:
    stmt = (
        select(MarketplaceListing)
        .join(MarketplaceListing.ownership)
        .join(GiftOwnership.item)
        .join(CollectionItem.collection)
        .where(
            MarketplaceListing.status == ListingStatus.ACTIVE.value,
            CollectionItem.is_tradeable.is_(True),
        )
        .options(
            joinedload(MarketplaceListing.ownership).joinedload(GiftOwnership.item).joinedload(CollectionItem.collection),
            joinedload(MarketplaceListing.seller),
        )
    )
    if filters.min_price is not None:
        stmt = stmt.where(MarketplaceListing.price_stars >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(MarketplaceListing.price_stars <= filters.max_price)
    return _apply_item_filters(stmt, filters)


def _primary_base(filters: MarketFilters) -> Select:
    stmt = (
        select(CollectionItem)
        .join(CollectionItem.collection)
        .where(
            CollectionItem.status == "active",
            CollectionItem.minted_count > 0,
            CollectionItem.minted_count < CollectionItem.edition_size,
            CollectionItem.collection.has(status="active"),
        )
        .options(joinedload(CollectionItem.collection).joinedload(Collection.category))
    )
    if filters.min_price is not None:
        stmt = stmt.where(CollectionItem.primary_price_stars >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(CollectionItem.primary_price_stars <= filters.max_price)
    return _apply_item_filters(stmt, filters)


def query_market(
    db: Session,
    filters: MarketFilters,
    *,
    kind: str = "all",
    sort: str = "recent",
    page: int = 1,
    page_size: int = 24,
    exclude_user_id: int | None = None,
) -> tuple[list[MarketCard], int]:
    """Return marketplace cards for resale listings merged with primary mints.

    Each source is read in its own sorted order; only the first
    ``page * page_size`` rows of each source can ever appear on the requested
    page, which keeps the merge correct and bounded in size.
    """
    window_end = page * page_size
    cards: list[MarketCard] = []

    if kind in {"all", "resale"}:
        stmt = _listing_base(filters)
        if exclude_user_id:
            stmt = stmt.where(MarketplaceListing.seller_id != exclude_user_id)
        if sort == "price_asc":
            stmt = stmt.order_by(MarketplaceListing.price_stars.asc(), MarketplaceListing.id.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(MarketplaceListing.price_stars.desc(), MarketplaceListing.id.desc())
        elif sort == "popular":
            stmt = stmt.order_by(MarketplaceListing.views.desc(), MarketplaceListing.listed_at.desc())
        elif sort == "rarity":
            stmt = stmt.order_by(RARITY_ORDER.desc(), MarketplaceListing.listed_at.desc())
        else:
            stmt = stmt.order_by(MarketplaceListing.listed_at.desc(), MarketplaceListing.id.desc())
        listings = db.scalars(stmt.limit(window_end)).unique().all()
        cards.extend(market_card_from_listing(listing) for listing in listings)

    if kind in {"all", "primary"}:
        stmt = _primary_base(filters)
        if sort == "price_asc":
            stmt = stmt.order_by(CollectionItem.primary_price_stars.asc(), CollectionItem.id.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(CollectionItem.primary_price_stars.desc(), CollectionItem.id.desc())
        elif sort == "popular":
            stmt = stmt.order_by(CollectionItem.minted_count.desc(), CollectionItem.id.desc())
        elif sort == "rarity":
            stmt = stmt.order_by(RARITY_ORDER.desc(), CollectionItem.created_at.desc())
        else:
            stmt = stmt.order_by(CollectionItem.created_at.desc(), CollectionItem.id.desc())
        items = db.scalars(stmt.limit(window_end)).unique().all()
        cards.extend(market_card_primary(item) for item in items)

    # Deterministic global ordering over the merged window.
    if sort == "price_asc":
        cards.sort(key=lambda c: (c.price_stars, c.key))
    elif sort == "price_desc":
        cards.sort(key=lambda c: (-c.price_stars, c.key))
    elif sort == "popular":
        cards.sort(key=lambda c: (-(c.views or 0) * 1000 - c.item.minted_count, c.key))
    elif sort == "rarity":
        rank = {r.value: index for index, r in enumerate(Rarity, start=1)}
        cards.sort(key=lambda c: (-rank.get(c.item.rarity, 0), -int(c.listed_at.timestamp()) if c.listed_at else 0))
    else:
        cards.sort(key=lambda c: (c.listed_at or c.item.created_at), reverse=True)

    total = len(cards)
    start = (page - 1) * page_size
    return cards[start : start + page_size], total


def active_listing_for_item(db: Session, item_id: int) -> MarketplaceListing | None:
    return db.scalar(
        select(MarketplaceListing)
        .join(MarketplaceListing.ownership)
        .where(
            GiftOwnership.item_id == item_id,
            MarketplaceListing.status == ListingStatus.ACTIVE.value,
        )
        .options(
            joinedload(MarketplaceListing.ownership).joinedload(GiftOwnership.item),
            joinedload(MarketplaceListing.seller),
        )
        .order_by(MarketplaceListing.price_stars.asc(), MarketplaceListing.listed_at.asc())
    )


def cheapest_listing_price(db: Session, item_id: int) -> int | None:
    return db.scalar(
        select(func.min(MarketplaceListing.price_stars))
        .join(MarketplaceListing.ownership)
        .where(
            GiftOwnership.item_id == item_id,
            MarketplaceListing.status == ListingStatus.ACTIVE.value,
        )
    )


def price_history(db: Session, item_id: int, limit: int = 40) -> list:
    rows = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.item_id == item_id)
        .order_by(PriceHistory.created_at.desc(), PriceHistory.id.desc())
        .limit(limit)
    ).all()
    return [price_point(row.event, row.price_stars, row.created_at, row.listing_id) for row in rows]


def sales_history(db: Session, item_id: int, limit: int = 20) -> list:
    rows = db.scalars(
        select(Order)
        .where(Order.item_id == item_id, Order.status == OrderStatus.FULFILLED.value)
        .order_by(Order.fulfilled_at.desc())
        .limit(limit)
    ).all()
    return [
        price_point(PriceEvent.SOLD.value, row.amount_stars, row.fulfilled_at or row.created_at)
        for row in rows
    ]


def owners_history(db: Session, ownership_id: int | None, item_id: int | None = None) -> list[dict]:
    stmt = (
        select(OwnershipHistory)
        .options(
            joinedload(OwnershipHistory.from_user),
            joinedload(OwnershipHistory.to_user),
        )
        .order_by(OwnershipHistory.created_at.asc())
    )
    if ownership_id:
        stmt = stmt.where(OwnershipHistory.ownership_id == ownership_id)
    elif item_id:
        stmt = stmt.join(GiftOwnership, GiftOwnership.id == OwnershipHistory.ownership_id).where(
            GiftOwnership.item_id == item_id
        )
    else:
        return []
    rows = db.scalars(stmt.limit(50)).all()
    return [
        {
            "event": row.event,
            "from": user_short(row.from_user),
            "to": user_short(row.to_user),
            "price_stars": row.price_stars,
            "created_at": row.created_at,
            "owner_id": row.ownership_id,
        }
        for row in rows
    ]


def collection_stats(db: Session, collection: Collection) -> tuple[int, int, int | None]:
    items_count = db.scalar(
        select(func.count(CollectionItem.id)).where(
            CollectionItem.collection_id == collection.id, CollectionItem.status != "draft"
        )
    ) or 0
    minted = db.scalar(
        select(func.count(GiftOwnership.id))
        .join(GiftOwnership.item)
        .where(CollectionItem.collection_id == collection.id)
    ) or 0
    floor = db.scalar(
        select(func.min(MarketplaceListing.price_stars))
        .join(MarketplaceListing.ownership)
        .join(GiftOwnership.item)
        .where(
            CollectionItem.collection_id == collection.id,
            MarketplaceListing.status == ListingStatus.ACTIVE.value,
        )
    )
    return items_count, minted, floor


def build_home(db: Session, *, user: User | None) -> HomeResponse:
    featured_items = db.scalars(
        select(CollectionItem)
        .where(
            CollectionItem.is_featured.is_(True),
            CollectionItem.status.in_(["active", "sold_out"]),
        )
        .options(joinedload(CollectionItem.collection))
        .order_by(CollectionItem.minted_count.desc())
        .limit(8)
    ).unique().all()
    if len(featured_items) < 8:
        extras = db.scalars(
            select(CollectionItem)
            .where(CollectionItem.status.in_(["active", "sold_out"]))
            .options(joinedload(CollectionItem.collection))
            .order_by(CollectionItem.minted_count.desc())
            .limit(8)
        ).unique().all()
        seen = {item.id for item in featured_items}
        featured_items = list(featured_items) + [item for item in extras if item.id not in seen]
        featured_items = featured_items[:8]

    trending, _ = query_market(db, MarketFilters(), sort="popular", page=1, page_size=8)
    new_arrivals = db.scalars(
        select(CollectionItem)
        .where(CollectionItem.status == "active")
        .options(joinedload(CollectionItem.collection))
        .order_by(CollectionItem.created_at.desc())
        .limit(10)
    ).unique().all()

    collection_rarity_order = case(
        {
            Rarity.RARE.value: 1,
            Rarity.EPIC.value: 2,
            Rarity.LEGENDARY.value: 3,
        },
        value=Collection.rarity,
        else_=0,
    )
    rare_collections = db.scalars(
        select(Collection)
        .where(
            Collection.status == "active",
            Collection.rarity.in_([Rarity.EPIC.value, Rarity.LEGENDARY.value, Rarity.RARE.value]),
        )
        .options(joinedload(Collection.category))
        .order_by(collection_rarity_order.desc(), Collection.created_at.desc())
        .limit(6)
    ).unique().all()

    recent_sales_rows = db.scalars(
        select(Order)
        .where(Order.status == OrderStatus.FULFILLED.value)
        .options(
            joinedload(Order.item),
            joinedload(Order.ownership),
        )
        .order_by(func.coalesce(Order.fulfilled_at, Order.created_at).desc())
        .limit(10)
    ).unique().all()
    recent_sales = [
        RecentSale(
            item_name=row.item.name,
            image_url=row.item.image_url,
            rarity=row.item.rarity,
            price_stars=row.amount_stars,
            sold_at=row.fulfilled_at or row.created_at,
            serial_number=row.ownership.serial_number if row.ownership else None,
        )
        for row in recent_sales_rows
    ]

    top_sellers = db.scalars(
        select(User)
        .where(User.sales_count > 0, User.is_blocked.is_(False))
        .order_by(User.sales_count.desc(), User.rating_sum.desc())
        .limit(8)
    ).all()

    exclude = user.id if user else None
    recommended, _ = query_market(
        db, MarketFilters(), sort="price_asc", page=1, page_size=8, exclude_user_id=exclude
    )

    since_24h = utcnow() - timedelta(hours=24)
    total_volume = db.scalar(
        select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
            Order.status == OrderStatus.FULFILLED.value
        )
    ) or 0
    sales_24h = db.scalar(
        select(func.count(Order.id)).where(
            Order.status == OrderStatus.FULFILLED.value, Order.fulfilled_at >= since_24h
        )
    ) or 0
    active_listings = db.scalar(
        select(func.count(MarketplaceListing.id)).where(
            MarketplaceListing.status == ListingStatus.ACTIVE.value
        )
    ) or 0
    collectors = db.scalar(select(func.count(User.id))) or 0

    return HomeResponse(
        featured=[item_card(item) for item in featured_items],
        trending=trending,
        new_arrivals=[item_card(item) for item in new_arrivals],
        rare_collections=[collection_public(c) for c in rare_collections],
        recent_sales=recent_sales,
        top_sellers=[user_short(user) for user in top_sellers],
        recommended=recommended,
        stats=HomeStats(
            total_volume_stars=int(total_volume),
            sales_24h=int(sales_24h),
            active_listings=int(active_listings),
            collectors=int(collectors),
        ),
    )


def is_favorite(db: Session, user_id: int | None, item_id: int) -> bool:
    if not user_id:
        return False
    return db.scalar(
        select(Favorite.id).where(Favorite.user_id == user_id, Favorite.item_id == item_id)
    ) is not None
