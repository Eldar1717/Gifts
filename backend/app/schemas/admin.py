"""Admin panel schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.enums import (
    AdminRole,
    CollectionStatus,
    GiftSource,
    GiftStatus,
    PayoutMethod,
    PayoutStatus,
    Rarity,
    ReportStatus,
    ReportTargetType,
)
from app.schemas.catalog import CollectionItemCard
from app.schemas.users import UserShort


class AdminOverview(BaseModel):
    total_volume_stars: int
    platform_revenue_stars: int
    seller_credits_stars: int
    orders_count: int
    orders_paid_count: int
    orders_fulfilled_count: int
    active_users_7d: int
    active_users_30d: int
    users_total: int
    active_listings: int
    collections_total: int
    gifts_minted: int
    pending_payouts_stars: int
    pending_payout_requests: int
    open_reports: int
    seller_pending_stars: int
    seller_available_stars: int
    revenue_24h_stars: int
    volume_24h_stars: int
    orders_24h: int
    top_gifts: list[dict]
    revenue_series: list[dict]
    recent_orders: list[dict]


class AdminUserRow(BaseModel):
    id: int
    telegram_id: int
    username: str
    display_name: str
    photo_url: str = ""
    is_admin: bool = False
    is_blocked: bool = False
    admin_role: str | None = None
    sales_count: int = 0
    purchases_count: int = 0
    gifts_owned: int = 0
    available_stars: int = 0
    pending_stars: int = 0
    created_at: datetime
    last_seen_at: datetime


class AdminUserUpdate(BaseModel):
    is_blocked: bool | None = None
    blocked_reason: str | None = Field(default=None, max_length=500)
    is_admin: bool | None = None
    admin_role: AdminRole | None = None


class AdminBalanceAdjustment(BaseModel):
    user_id: int
    amount_stars: int
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("amount_stars")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Сумма корректировки не может быть нулевой")
        return value


class CategoryCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    emoji: str = Field(default="", max_length=16)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    emoji: str | None = Field(default=None, max_length=16)
    sort_order: int | None = None
    is_active: bool | None = None


class CollectionCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=4000)
    cover_url: str = Field(default="", max_length=2000)
    accent: str = Field(default="#7c5cff", max_length=16)
    category_id: int | None = None
    rarity: Rarity = Rarity.COMMON
    status: CollectionStatus = CollectionStatus.DRAFT
    is_featured: bool = False
    released_at: datetime | None = None
    ton_collection_address: str = Field(default="", max_length=80)


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    cover_url: str | None = Field(default=None, max_length=2000)
    accent: str | None = Field(default=None, max_length=16)
    category_id: int | None = None
    rarity: Rarity | None = None
    status: CollectionStatus | None = None
    is_featured: bool | None = None
    released_at: datetime | None = None
    ton_collection_address: str | None = Field(default=None, max_length=80)


class ItemCreate(BaseModel):
    collection_id: int
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=4000)
    image_url: str = Field(default="", max_length=2000)
    back_image_url: str = Field(default="", max_length=2000)
    glow: str = Field(default="#7c5cff", max_length=16)
    rarity: Rarity = Rarity.COMMON
    edition_size: int = Field(default=100, ge=1, le=1_000_000)
    primary_price_stars: int = Field(ge=1, le=1_000_000)
    is_limited: bool = True
    is_serialized: bool = True
    status: GiftStatus = GiftStatus.DRAFT
    source: GiftSource = GiftSource.INTERNAL
    is_tradeable: bool = True
    is_featured: bool = False
    external_url: str = Field(default="", max_length=2000)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    image_url: str | None = Field(default=None, max_length=2000)
    back_image_url: str | None = Field(default=None, max_length=2000)
    glow: str | None = Field(default=None, max_length=16)
    rarity: Rarity | None = None
    primary_price_stars: int | None = Field(default=None, ge=1, le=1_000_000)
    status: GiftStatus | None = None
    is_tradeable: bool | None = None
    is_featured: bool | None = None
    external_url: str | None = Field(default=None, max_length=2000)


class SettingsUpdate(BaseModel):
    commission_percent: int | None = Field(default=None, ge=0, le=50)
    min_listing_price: int | None = Field(default=None, ge=1, le=100_000)
    max_listing_price: int | None = Field(default=None, ge=1, le=10_000_000)
    hold_hours: float | None = Field(default=None, ge=0, le=720)
    maintenance_mode: bool | None = None
    maintenance_message: str | None = Field(default=None, max_length=280)
    max_active_listings: int | None = Field(default=None, ge=1, le=1000)
    payout_note: str | None = Field(default=None, max_length=2000)
    terms_url: str | None = Field(default=None, max_length=2000)

    @field_validator("max_listing_price")
    @classmethod
    def _max_price(cls, value: int | None) -> int | None:
        return value


class AdminSettingsPublic(BaseModel):
    commission_percent: int
    min_listing_price: int
    max_listing_price: int
    hold_hours: float
    maintenance_mode: bool
    maintenance_message: str
    max_active_listings: int
    min_payout_stars: int = 100
    payout_note: str
    terms_url: str
    updated_at: datetime
    updated_by: UserShort | None = None


class GiftGrant(BaseModel):
    user_id: int
    item_id: int
    quantity: int = Field(default=1, ge=1, le=50)
    reason: str = Field(default="", max_length=200)


class PayoutDecision(BaseModel):
    status: Literal["approved", "rejected", "paid"]
    admin_note: str = Field(default="", max_length=500)
    external_reference: str = Field(default="", max_length=160)


class PayoutRow(BaseModel):
    id: int
    user: UserShort
    amount_stars: int
    method: PayoutMethod
    destination: str
    status: PayoutStatus
    admin_note: str
    external_reference: str
    created_at: datetime
    decided_at: datetime | None = None
    paid_at: datetime | None = None


class ReportRow(BaseModel):
    id: int
    reporter: UserShort
    target_type: ReportTargetType
    target_id: int
    reason: str
    details: str
    status: ReportStatus
    resolution: str
    created_at: datetime
    resolved_at: datetime | None = None


class ReportResolve(BaseModel):
    status: Literal["reviewing", "resolved", "dismissed"]
    resolution: str = Field(default="", max_length=1000)


class AuditLogRow(BaseModel):
    id: int
    admin: UserShort | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    before: str = ""
    after: str = ""
    ip_address: str = ""
    created_at: datetime


class AdminListingRow(BaseModel):
    id: int
    item: CollectionItemCard
    seller: UserShort
    price_stars: int
    status: str
    listed_at: datetime
    views: int = 0


class AdminOrderRow(BaseModel):
    id: int
    order_number: str
    item_name: str
    image_url: str = ""
    buyer: UserShort
    seller: UserShort | None = None
    amount_stars: int
    commission_stars: int
    seller_amount_stars: int
    status: str
    created_at: datetime
    paid_at: datetime | None = None


class AdminItemRow(BaseModel):
    item: CollectionItemCard
    collection_name: str
    minted_count: int
    edition_size: int


class Withdrawable(BaseModel):
    available_stars: int
    minimum_stars: int = 1
