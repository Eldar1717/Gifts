"""Order, payment and invoice schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import OrderStatus, OrderType, PaymentStatus
from app.schemas.catalog import CollectionItemCard
from app.schemas.users import UserShort


class InvoiceRequest(BaseModel):
    """Either a resale ``listing_id`` or a primary ``item_id`` is required.

    The price is never accepted from the client: the backend reads it from the
    listing or from the collection item definition.
    """

    listing_id: int | None = Field(default=None, gt=0)
    item_id: int | None = Field(default=None, gt=0)

    def model_post_init(self, __context) -> None:  # pragma: no cover - validation helper
        if (self.listing_id is None) == (self.item_id is None):
            raise ValueError("Provide exactly one of listing_id or item_id")


class InvoiceResponse(BaseModel):
    order_id: int
    order_number: str
    amount_stars: int
    currency: str = "XTR"
    status: OrderStatus
    invoice_url: str
    expires_at: datetime | None = None
    commission_stars: int = 0
    seller_amount_stars: int = 0
    item_name: str
    dev_simulated: bool = False


class OrderPublic(BaseModel):
    id: int
    order_number: str
    status: OrderStatus
    order_type: OrderType
    amount_stars: int
    commission_stars: int
    seller_amount_stars: int
    currency: str = "XTR"
    created_at: datetime
    paid_at: datetime | None = None
    fulfilled_at: datetime | None = None
    item: CollectionItemCard
    seller: UserShort | None = None
    buyer: UserShort | None = None
    serial_number: int | None = None
    reviewed: bool = False
    can_review: bool = False
    failure_reason: str = ""


class PaymentPublic(BaseModel):
    id: int
    status: PaymentStatus
    amount_stars: int
    currency: str
    telegram_payment_charge_id: str | None = None
    provider_payment_charge_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime


class OrderDetail(OrderPublic):
    payment: PaymentPublic | None = None


class DevPayRequest(BaseModel):
    """Available only when DEV_AUTH is enabled outside production."""

    order_id: int
