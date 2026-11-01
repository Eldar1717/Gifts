"""User, profile, balance and notification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import LedgerBucket, NotificationType, PayoutMethod, TransactionType
from app.schemas.common import ORMModel


class UserPublic(ORMModel):
    id: int
    telegram_id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    photo_url: str = ""
    display_name: str = ""
    rating: float | None = None
    sales_count: int = 0
    purchases_count: int = 0
    created_at: datetime


class UserShort(BaseModel):
    id: int
    username: str = ""
    display_name: str
    photo_url: str = ""
    rating: float | None = None


class PrivacySettings(BaseModel):
    show_collection: bool = True
    allow_offers: bool = True
    notify_sales: bool = True
    notify_market: bool = False


class ProfileSettingsUpdate(BaseModel):
    show_collection: bool | None = None
    allow_offers: bool | None = None
    notify_sales: bool | None = None
    notify_market: bool | None = None


class TonWalletUpdate(BaseModel):
    address: str = Field(default="", max_length=80)

    @field_validator("address")
    @classmethod
    def _validate_address(cls, value: str) -> str:
        value = value.strip()
        if value and not (value.startswith(("EQ", "UQ", "0:")) and len(value) >= 3):
            raise ValueError("TON address must start with EQ… or UQ… (friendly format)")
        return value


class BalancePublic(BaseModel):
    currency: str = "XTR"
    pending_stars: int = 0
    available_stars: int = 0
    withdrawn_stars: int = 0
    lifetime_stars: int = 0
    hold_hours: float = 72
    can_request_payout: bool = False
    payout_note: str = ""


class StatsPublic(BaseModel):
    gifts_owned: int = 0
    listings_active: int = 0
    sales_count: int = 0
    purchases_count: int = 0
    gross_sales_stars: int = 0
    gross_purchases_stars: int = 0
    lifetime_seller_stars: int = 0
    rating_count: int = 0
    rating: float | None = None


class MeResponse(BaseModel):
    user: UserPublic
    is_admin: bool = False
    admin_role: str | None = None
    settings: PrivacySettings
    ton_address: str = ""
    stats: StatsPublic
    balance: BalancePublic
    unread_notifications: int = 0


class SellerProfileResponse(BaseModel):
    user: UserShort
    stats: StatsPublic
    listings_count: int
    collection_visible: bool
    recently_sold: list[str] = []


class TransactionPublic(ORMModel):
    id: int
    type: TransactionType
    bucket: LedgerBucket
    amount_stars: int
    balance_after: int | None = None
    description: str = ""
    order_id: int | None = None
    created_at: datetime


class NotificationPublic(ORMModel):
    id: int
    type: NotificationType
    title: str
    body: str
    payload: str
    is_read: bool
    created_at: datetime


class PayoutCreate(BaseModel):
    amount_stars: int = Field(ge=1, le=1_000_000)
    method: PayoutMethod = PayoutMethod.STARS_MANUAL
    destination: str = Field(default="", max_length=160)


class PayoutPublic(ORMModel):
    id: int
    user_id: int
    amount_stars: int
    method: PayoutMethod
    destination: str
    status: str
    admin_note: str
    created_at: datetime
    decided_at: datetime | None = None
    paid_at: datetime | None = None
