"""Domain enumerations shared by models, schemas and services."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value


class Rarity(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class CollectionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class GiftStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SOLD_OUT = "sold_out"
    ARCHIVED = "archived"


class GiftSource(StrEnum):
    """Where a collectible comes from.

    ``internal`` items are issued by GIFT MARKET and live in our database only.
    The other values are explicit labels for externally verifiable assets; we
    never call an internal item an NFT.
    """

    INTERNAL = "internal"
    TELEGRAM_OFFICIAL = "telegram_official"
    EXTERNAL_NFT = "external_nft"


class OwnershipStatus(StrEnum):
    OWNED = "owned"
    BURNED = "burned"


class AcquisitionType(StrEnum):
    PRIMARY = "primary"
    RESALE = "resale"
    ADMIN_GRANT = "admin_grant"


class OwnershipEvent(StrEnum):
    MINT = "mint"
    RESALE = "resale"
    ADMIN_GRANT = "admin_grant"
    TRANSFER = "transfer"


class ListingStatus(StrEnum):
    ACTIVE = "active"
    RESERVED = "reserved"
    SOLD = "sold"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderType(StrEnum):
    PRIMARY = "primary"
    RESALE = "resale"


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    FULFILLED = "fulfilled"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(StrEnum):
    TELEGRAM_STARS = "telegram_stars"


class RefundStatus(StrEnum):
    REQUESTED = "requested"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TransactionType(StrEnum):
    SALE_CREDIT = "sale_credit"
    COMMISSION = "commission"
    REFUND_DEBIT = "refund_debit"
    SETTLEMENT = "settlement"
    PAYOUT_REQUEST = "payout_request"
    PAYOUT_REVERSAL = "payout_reversal"
    PAYOUT_PAID = "payout_paid"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class LedgerBucket(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    PLATFORM = "platform"
    PAYOUT = "payout"
    EXTERNAL = "external"


class PayoutStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class PayoutMethod(StrEnum):
    STARS_MANUAL = "stars_manual"
    BANK_MANUAL = "bank_manual"
    TON_MANUAL = "ton_manual"


class AdminRole(StrEnum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    SUPPORT = "support"


class NotificationType(StrEnum):
    PURCHASE = "purchase"
    SALE = "sale"
    LISTING_CREATED = "listing_created"
    LISTING_CANCELLED = "listing_cancelled"
    PAYMENT_STATUS = "payment_status"
    SELLER_CREDIT = "seller_credit"
    PAYOUT = "payout"
    OFFER = "offer"
    SYSTEM = "system"
    ADMIN = "admin"


class ReportTargetType(StrEnum):
    GIFT = "gift"
    LISTING = "listing"
    USER = "user"
    ORDER = "order"


class ReportStatus(StrEnum):
    OPEN = "open"
    REVIEWING = "reviewing"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class PriceEvent(StrEnum):
    LISTED = "listed"
    PRICE_CHANGED = "price_changed"
    SOLD = "sold"
    CANCELLED = "cancelled"


class PriceHistoryScope(StrEnum):
    GIFT = "gift"
    OWNERSHIP = "ownership"
