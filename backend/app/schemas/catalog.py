"""Collection, gift and marketplace schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.enums import GiftSource, GiftStatus, Rarity
from app.schemas.common import ORMModel
from app.schemas.users import UserShort

RarityLiteral = Literal["common", "uncommon", "rare", "epic", "legendary"]


class CategoryPublic(ORMModel):
    id: int
    slug: str
    name: str
    emoji: str = ""
    description: str = ""
    sort_order: int = 0


class CollectionShort(ORMModel):
    id: int
    slug: str
    name: str
    rarity: Rarity
    cover_url: str = ""
    accent: str = "#7c5cff"


class CollectionPublic(CollectionShort):
    description: str = ""
    status: str
    is_featured: bool
    released_at: datetime | None = None
    category: CategoryPublic | None = None
    ton_collection_address: str = ""
    chain_verified: bool = False
    items_count: int = 0
    items_sold: int = 0
    floor_price_stars: int | None = None


class CollectionItemCard(ORMModel):
    id: int
    name: str
    image_url: str = ""
    back_image_url: str = ""
    rarity: Rarity
    glow: str = "#7c5cff"
    primary_price_stars: int
    edition_size: int
    minted_count: int = 0
    remaining: int = 0
    status: GiftStatus = GiftStatus.ACTIVE
    source: GiftSource = GiftSource.INTERNAL
    is_tradeable: bool = True
    is_featured: bool = False
    collection: CollectionShort
    created_at: datetime


class OwnershipShort(BaseModel):
    id: int
    serial_number: int | None = None
    owner: UserShort
    acquired_at: datetime
    acquired_price_stars: int = 0


class ListingShort(BaseModel):
    id: int
    price_stars: int
    status: str
    listed_at: datetime
    seller: UserShort


class MarketCard(BaseModel):
    """A marketplace row: either a primary (mint) offer or a resale listing."""

    kind: Literal["primary", "resale"]
    key: str
    item: CollectionItemCard
    listing_id: int | None = None
    ownership_id: int | None = None
    price_stars: int
    seller: UserShort | None = None
    serial_number: int | None = None
    listed_at: datetime | None = None
    views: int = 0


class PricePoint(BaseModel):
    price_stars: int
    event: str
    created_at: datetime
    listing_id: int | None = None


class ItemDetail(MarketCard):
    description: str = ""
    collection: CollectionPublic
    price_history: list[PricePoint] = []
    recent_sales: list[PricePoint] = []
    owners_history: list[dict] = []
    favorite: bool = False
    owned_by_me: bool = False
    can_buy: bool = False
    remaining: int = 0
    edition_size: int = 0
    minted_count: int = 0


class MarketQuery(BaseModel):
    q: str | None = Field(default=None, max_length=80)
    collection: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=64)
    rarity: list[RarityLiteral] | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    kind: Literal["all", "primary", "resale"] = "all"
    sort: Literal["recent", "price_asc", "price_desc", "popular", "rarity"] = "recent"
    page: int = Field(default=1, ge=1, le=500)
    page_size: int = Field(default=24, ge=1, le=60)


class MarketplaceConfig(BaseModel):
    commission_percent: int
    seller_share_percent: int
    min_listing_price: int
    max_listing_price: int
    hold_hours: float
    min_payout_stars: int = 100
    currency: str = "XTR"
    seller_balance_type: str = "internal_ledger"
    payout_note: str = ""
    maintenance_mode: bool = False
    maintenance_message: str = ""


class ListingCreate(BaseModel):
    ownership_id: int = Field(gt=0)
    price_stars: int = Field(gt=0, le=1_000_000)


class ListingUpdate(BaseModel):
    price_stars: int = Field(gt=0, le=1_000_000)


class ListingPublic(BaseModel):
    id: int
    price_stars: int
    status: str
    listed_at: datetime
    reserved_until: datetime | None = None
    views: int = 0
    seller: UserShort
    ownership: OwnershipShort
    item: CollectionItemCard


class ListingCreated(BaseModel):
    listing: ListingPublic
    commission_percent: int
    seller_receives_stars: int


class HomeStats(BaseModel):
    total_volume_stars: int = 0
    sales_24h: int = 0
    active_listings: int = 0
    collectors: int = 0


class RecentSale(BaseModel):
    item_name: str
    image_url: str
    rarity: Rarity
    price_stars: int
    sold_at: datetime
    serial_number: int | None = None


class HomeResponse(BaseModel):
    featured: list[CollectionItemCard] = []
    trending: list[MarketCard] = []
    new_arrivals: list[CollectionItemCard] = []
    rare_collections: list[CollectionPublic] = []
    recent_sales: list[RecentSale] = []
    top_sellers: list[UserShort] = []
    recommended: list[MarketCard] = []
    stats: HomeStats


class OwnershipCard(BaseModel):
    id: int
    serial_number: int | None = None
    acquired_at: datetime
    acquired_price_stars: int = 0
    acquisition_type: str
    status: str
    item: CollectionItemCard
    listing: ListingShort | None = None
    can_list: bool = False
    estimated_value_stars: int | None = None


class OwnershipDetail(OwnershipCard):
    history: list[dict] = []
    price_history: list[PricePoint] = []


class FavoriteToggle(BaseModel):
    item_id: int
    favorite: bool


class ReviewCreate(BaseModel):
    order_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)

    @field_validator("comment")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class ReviewPublic(BaseModel):
    id: int
    rating: int
    comment: str
    created_at: datetime
    author: UserShort


class OfferCreate(BaseModel):
    ownership_id: int
    price_stars: int = Field(gt=0, le=1_000_000)
    message: str = Field(default="", max_length=280)


class OfferPublic(BaseModel):
    id: int
    ownership_id: int
    price_stars: int
    message: str
    status: str
    created_at: datetime
    buyer: UserShort
    item_name: str
    image_url: str = ""


class ReportCreate(BaseModel):
    target_type: Literal["gift", "listing", "user", "order"]
    target_id: int
    reason: str = Field(min_length=3, max_length=64)
    details: str = Field(default="", max_length=1000)


class TonVerifyRequest(BaseModel):
    collection_address: str = Field(min_length=3, max_length=80)
