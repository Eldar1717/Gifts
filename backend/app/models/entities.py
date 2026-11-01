"""SQLAlchemy ORM models for GIFT MARKET.

Naming and structure follow the domain language of the product:
users own *gifts* (``gift_ownership`` rows), a gift belongs to a *collection*
via ``collection_items``, sellers publish *listings*, buyers create *orders*
paid through *payments*, money movement is recorded in ``transactions`` and
summarised per seller in ``seller_balances``.

Money is always an integer number of Telegram Stars (XTR). Financial rows are
append-only: no balance is ever recalculated from client input.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AdminRole,
    AcquisitionType,
    CollectionStatus,
    GiftSource,
    GiftStatus,
    ListingStatus,
    NotificationType,
    OrderStatus,
    OrderType,
    OwnershipEvent,
    OwnershipStatus,
    PaymentProvider,
    PaymentStatus,
    PayoutMethod,
    PayoutStatus,
    PriceHistoryScope,
    Rarity,
    RefundStatus,
    ReportStatus,
    ReportTargetType,
)
from app.db.base import Base, TimestampMixin, utcnow


# ---------------------------------------------------------------------------
# Users & profile
# ---------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    photo_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Privacy settings
    show_collection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_offers: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_sales: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_market: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # TON integration (optional; we only ever store a public address)
    ton_address: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    ton_address_verified_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # Supplier counters (denormalised for fast marketplace cards)
    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    purchases_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_seen_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    balance: Mapped["SellerBalance | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_username", "username"),
        CheckConstraint("sales_count >= 0 AND purchases_count >= 0", name="ck_users_counters"),
    )

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or (f"@{self.username}" if self.username else f"User {self.telegram_id}")

    @property
    def rating(self) -> float | None:
        if not self.rating_count:
            return None
        return round(self.rating_sum / self.rating_count, 2)


class AdminUser(TimestampMixin, Base):
    """Elevated role layered on top of a Telegram user."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    role: Mapped[str] = mapped_column(String(20), default=AdminRole.ADMIN.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(lazy="joined")


class UserSettings(Base):
    """Reserved for forward-compatible per-user preferences."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    locale: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    accent: Mapped[str] = mapped_column(String(16), default="#7c5cff", nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rarity: Mapped[str] = mapped_column(String(16), default=Rarity.COMMON.value, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=CollectionStatus.ACTIVE.value, nullable=False
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # Optional on-chain metadata. Only filled after a real mint is confirmed.
    ton_collection_address: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    chain_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[Category | None] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_collections_status_featured", "status", "is_featured"),
        CheckConstraint(
            "rarity IN ('common','uncommon','rare','epic','legendary')",
            name="ck_collections_rarity",
        ),
    )


class CollectionItem(TimestampMixin, Base):
    """A gift definition inside a collection (the "template")."""

    __tablename__ = "collection_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    back_image_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    glow: Mapped[str] = mapped_column(String(16), default="#7c5cff", nullable=False)
    rarity: Mapped[str] = mapped_column(String(16), default=Rarity.COMMON.value, nullable=False)
    rarity_weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    edition_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    minted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    primary_price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    is_limited: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_serialized: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    status: Mapped[str] = mapped_column(String(16), default=GiftStatus.ACTIVE.value, nullable=False)
    source: Mapped[str] = mapped_column(String(24), default=GiftSource.INTERNAL.value, nullable=False)
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    external_url: Mapped[str] = mapped_column(Text, default="", nullable=False)

    collection: Mapped[Collection] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("collection_id", "name", name="uq_collection_items_name"),
        Index("ix_collection_items_rarity_status", "rarity", "status"),
        Index("ix_collection_items_created", "created_at"),
        CheckConstraint(
            "rarity IN ('common','uncommon','rare','epic','legendary')",
            name="ck_collection_items_rarity",
        ),
        CheckConstraint("edition_size > 0", name="ck_collection_items_edition"),
        CheckConstraint("minted_count >= 0", name="ck_collection_items_minted"),
        CheckConstraint("primary_price_stars > 0", name="ck_collection_items_price"),
    )

    @property
    def remaining(self) -> int:
        return max(0, self.edition_size - self.minted_count)


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------
class GiftOwnership(TimestampMixin, Base):
    """One concrete instance of a collection item owned by a user."""

    __tablename__ = "gift_ownership"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("collection_items.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    serial_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=OwnershipStatus.OWNED.value, nullable=False)
    acquisition_type: Mapped[str] = mapped_column(
        String(16), default=AcquisitionType.PRIMARY.value, nullable=False
    )
    acquired_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)
    acquired_price_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    item: Mapped[CollectionItem] = relationship(lazy="joined")
    owner: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("item_id", "serial_number", name="uq_ownership_item_serial"),
        Index("ix_ownership_owner_status", "owner_id", "status"),
        Index("ix_ownership_item_acquired", "item_id", "acquired_at"),
        CheckConstraint("serial_number IS NULL OR serial_number > 0", name="ck_ownership_serial"),
    )


class OwnershipHistory(Base):
    """Append-only chain of owners of every collectible."""

    __tablename__ = "ownership_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ownership_id: Mapped[int] = mapped_column(
        ForeignKey("gift_ownership.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(20), default=OwnershipEvent.MINT.value, nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    from_user: Mapped[User | None] = relationship(foreign_keys=[from_user_id], lazy="joined")
    to_user: Mapped[User] = relationship(foreign_keys=[to_user_id], lazy="joined")

    __table_args__ = (
        Index("ix_ownership_history_ownership_created", "ownership_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------
class MarketplaceListing(TimestampMixin, Base):
    __tablename__ = "marketplace_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ownership_id: Mapped[int] = mapped_column(
        ForeignKey("gift_ownership.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ListingStatus.ACTIVE.value, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Reservation created when a buyer opens an invoice (anti double-sale).
    reserved_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    sold_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    listed_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    ownership: Mapped[GiftOwnership] = relationship(lazy="joined")
    seller: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        # A collectible can be relisted over time (history is kept), but only one
        # active/reserved listing may exist per ownership. Partial unique index.
        Index(
            "uq_listing_active_ownership",
            "ownership_id",
            unique=True,
            postgresql_where=text("status IN ('active','reserved')"),
            sqlite_where=text("status IN ('active','reserved')"),
        ),
        Index("ix_listings_status_price", "status", "price_stars"),
        Index("ix_listings_status_listed", "status", "listed_at"),
        Index("ix_listings_seller_status", "seller_id", "status"),
        CheckConstraint("price_stars > 0", name="ck_listings_price"),
        CheckConstraint(
            "status IN ('active','reserved','sold','cancelled','expired')",
            name="ck_listings_status",
        ),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("collection_items.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ownership_id: Mapped[int | None] = mapped_column(
        ForeignKey("gift_ownership.id", ondelete="SET NULL"), nullable=True, index=True
    )
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="SET NULL"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(16), default=PriceHistoryScope.GIFT.value, nullable=False)
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_price_history_item_created", "item_id", "created_at"),)


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("collection_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    item: Mapped[CollectionItem] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_favorites_user_item"),
        Index("ix_favorites_user_created", "user_id", "created_at"),
    )


class Offer(TimestampMixin, Base):
    """Buyer proposal sent to the owner of a gift that is not listed."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ownership_id: Mapped[int] = mapped_column(
        ForeignKey("gift_ownership.id", ondelete="CASCADE"), index=True, nullable=False
    )
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(String(280), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id], lazy="joined")
    seller: Mapped[User] = relationship(foreign_keys=[seller_id], lazy="joined")
    ownership: Mapped[GiftOwnership] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_offers_seller_status", "seller_id", "status"),
        CheckConstraint("price_stars > 0", name="ck_offers_price"),
    )


# ---------------------------------------------------------------------------
# Orders, payments, refunds
# ---------------------------------------------------------------------------
class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    seller_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("collection_items.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    ownership_id: Mapped[int | None] = mapped_column(
        ForeignKey("gift_ownership.id", ondelete="SET NULL"), nullable=True
    )
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="SET NULL"), nullable=True
    )

    order_type: Mapped[str] = mapped_column(String(16), default=OrderType.PRIMARY.value, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=OrderStatus.PENDING_PAYMENT.value, nullable=False, index=True
    )

    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XTR", nullable=False)
    commission_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commission_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seller_amount_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id], lazy="joined")
    seller: Mapped[User | None] = relationship(foreign_keys=[seller_id], lazy="joined")
    item: Mapped[CollectionItem] = relationship(lazy="joined")
    ownership: Mapped[GiftOwnership | None] = relationship(lazy="joined")
    payment: Mapped["Payment | None"] = relationship(back_populates="order", uselist=False)

    __table_args__ = (
        Index("ix_orders_buyer_created", "buyer_id", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
        CheckConstraint("amount_stars > 0", name="ck_orders_amount"),
        CheckConstraint(
            "commission_stars >= 0 AND seller_amount_stars >= 0 "
            "AND commission_stars + seller_amount_stars = amount_stars",
            name="ck_orders_split",
        ),
        CheckConstraint(
            "status IN ('pending_payment','paid','fulfilled','failed','cancelled',"
            "'expired','refund_pending','refunded')",
            name="ck_orders_status",
        ),
    )


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(
        String(24), default=PaymentProvider.TELEGRAM_STARS.value, nullable=False
    )
    invoice_payload: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XTR", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING.value, nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    raw_update: Mapped[str] = mapped_column(Text, default="", nullable=False)

    order: Mapped[Order] = relationship(back_populates="payment")

    __table_args__ = (
        Index("ix_payments_status_created", "status", "created_at"),
        CheckConstraint("amount_stars > 0", name="ck_payments_amount"),
    )


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RefundStatus.REQUESTED.value, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    telegram_refund_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    __table_args__ = (
        Index("ix_refunds_status_created", "status", "created_at"),
        CheckConstraint("amount_stars > 0", name="ck_refunds_amount"),
    )


# ---------------------------------------------------------------------------
# Financial ledger
# ---------------------------------------------------------------------------
class Transaction(Base):
    """Append-only journal of every value movement inside the marketplace."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )
    payout_id: Mapped[int | None] = mapped_column(
        ForeignKey("payout_requests.id", ondelete="SET NULL"), nullable=True
    )
    refund_id: Mapped[int | None] = mapped_column(
        ForeignKey("refunds.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(28), nullable=False)
    bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(String(280), default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False, index=True)

    user: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_transactions_user_created", "user_id", "created_at"),
        Index("ix_transactions_type_created", "type", "created_at"),
        CheckConstraint("amount_stars <> 0", name="ck_transactions_amount"),
    )


class SellerBalance(TimestampMixin, Base):
    """Cached balance, always reconstructable from ``transactions``.

    pending  -> credited by a sale, held for the dispute window.
    available-> released after the hold, eligible for a payout request.
    lifetime -> cumulative seller income (audit convenience only).
    """

    __tablename__ = "seller_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    pending_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    withdrawn_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XTR", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="balance")

    __table_args__ = (
        CheckConstraint(
            "pending_stars >= 0 AND available_stars >= 0 AND withdrawn_stars >= 0",
            name="ck_seller_balances_non_negative",
        ),
    )


class PlatformSettings(Base):
    """Single-row (id=1) runtime configuration editable from the admin panel."""

    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    commission_percent: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    min_listing_price: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_listing_price: Mapped[int] = mapped_column(Integer, default=100_000, nullable=False)
    hold_hours: Mapped[float] = mapped_column(Float, default=72.0, nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintenance_message: Mapped[str] = mapped_column(String(280), default="", nullable=False)
    max_active_listings: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    min_payout_stars: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    payout_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    terms_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 50", name="ck_settings_commission"
        ),
        CheckConstraint("min_listing_price > 0", name="ck_settings_min_price"),
        CheckConstraint("max_listing_price >= min_listing_price", name="ck_settings_max_price"),
        CheckConstraint("min_payout_stars > 0", name="ck_settings_min_payout"),
    )


class PayoutRequest(TimestampMixin, Base):
    """Manual payout workflow: platform never auto-transfers Stars/TON."""

    __tablename__ = "payout_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(24), default=PayoutMethod.STARS_MANUAL.value, nullable=False)
    destination: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PayoutStatus.REQUESTED.value, nullable=False)
    admin_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    external_reference: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")

    __table_args__ = (
        Index("ix_payouts_status_created", "status", "created_at"),
        CheckConstraint("amount_stars > 0", name="ck_payouts_amount"),
    )


# ---------------------------------------------------------------------------
# Social: reviews, notifications, reports
# ---------------------------------------------------------------------------
class Review(TimestampMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    author: Mapped[User] = relationship(foreign_keys=[author_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating"),
        Index("ix_reviews_seller_created", "seller_id", "created_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(24), default=NotificationType.SYSTEM.value, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    telegram_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),)


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(16), default=ReportTargetType.LISTING.value, nullable=False
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ReportStatus.OPEN.value, nullable=False)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id], lazy="joined")

    __table_args__ = (Index("ix_reports_status_created", "status", "created_at"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before: Mapped[str] = mapped_column(Text, default="", nullable=False)
    after: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False, index=True)

    admin: Mapped[User | None] = relationship(foreign_keys=[admin_user_id], lazy="joined")

    __table_args__ = (Index("ix_audit_logs_action_created", "action", "created_at"),)


class WebhookEvent(Base):
    """Raw Telegram updates for idempotency and forensic replay."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    update_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    update_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class JobLock(Base):
    """Single-flight lock for background workers."""

    __tablename__ = "job_locks"

    name: Mapped[str] = mapped_column(String(48), primary_key=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    holder: Mapped[str] = mapped_column(String(64), default="", nullable=False)


# Re-exported for convenience in type hints
__all__ = [
    "AdminUser",
    "AuditLog",
    "Base",
    "Category",
    "Collection",
    "CollectionItem",
    "Favorite",
    "GiftOwnership",
    "JobLock",
    "MarketplaceListing",
    "Notification",
    "Offer",
    "Order",
    "OwnershipHistory",
    "Payment",
    "PayoutRequest",
    "PlatformSettings",
    "PriceHistory",
    "Refund",
    "Report",
    "Review",
    "SellerBalance",
    "Transaction",
    "User",
    "UserSettings",
    "WebhookEvent",
]
