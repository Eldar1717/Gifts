"""Checkout, payment verification, fulfilment and refunds.

State machine for an order::

    pending_payment -> paid -> fulfilled
                    \\-> expired / cancelled
    paid -> refund_pending -> refunded

Ownership transfer, listing state and ledger entries happen inside a single
database transaction guarded by row locks (PostgreSQL), so an item can never be
sold twice and a price can never be injected by the client.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import (
    ListingStatus,
    NotificationType,
    OrderStatus,
    OrderType,
    OwnershipStatus,
    PaymentStatus,
    PriceEvent,
    PriceHistoryScope,
    RefundStatus,
)
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import lock_row
from app.models import (
    CollectionItem,
    GiftOwnership,
    MarketplaceListing,
    Order,
    Payment,
    PriceHistory,
    Refund,
    User,
)
from app.services import ledger, notifications, ownership as ownership_service, telegram_bot
from app.services.marketplace import release_expired_reservations, reserve_listing
from app.services.platform import get_platform_settings
from app.services.pricing import Split, split_amount

logger = get_logger(__name__)


class CheckoutError(Exception):
    """Client-facing problem, mapped to HTTP 4xx by the router."""


class DeliveryError(Exception):
    """The paid order cannot be fulfilled; triggers an automatic refund."""


class FraudError(Exception):
    """Payment data does not match the order; requires investigation."""


@dataclass
class CheckoutResult:
    order: Order
    payment: Payment
    dev_simulated: bool = False
    notifications: list[int] = field(default_factory=list)


@dataclass
class FulfillResult:
    order: Order
    refund: Refund | None = None
    notifications: list[int] = field(default_factory=list)


def _order_number() -> str:
    return f"GM-{utcnow():%y%m%d}-{secrets.token_hex(3).upper()}"


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------
def create_checkout(
    db: Session, *, user: User, listing_id: int | None = None, item_id: int | None = None
) -> CheckoutResult:
    if user.is_blocked:
        raise CheckoutError("Аккаунт заблокирован, покупки недоступны")
    platform = get_platform_settings(db)
    if platform.maintenance_mode:
        raise CheckoutError(platform.maintenance_message or "Маркетплейс на обслуживании")

    release_expired_reservations(db)

    listing: MarketplaceListing | None = None
    item: CollectionItem
    seller_id: int | None = None
    ownership_id: int | None = None
    order_type = OrderType.PRIMARY
    amount = 0
    commission_percent = 100

    if listing_id is not None:
        listing = lock_row(db, MarketplaceListing, MarketplaceListing.id == listing_id).first()
        if listing is None:
            raise CheckoutError("Объявление не найдено")
        if listing.status != ListingStatus.ACTIVE.value:
            raise CheckoutError("Объявление уже недоступно")
        if listing.seller_id == user.id:
            raise CheckoutError("Нельзя купить собственный подарок")
        if listing.seller.is_blocked:
            raise CheckoutError("Продавец временно недоступен")
        item = listing.ownership.item
        if listing.ownership.owner_id != listing.seller_id:
            raise CheckoutError("Владелец предмета изменился, обновите ленту")
        if not item.is_tradeable:
            raise CheckoutError("Этот предмет нельзя перепродать")
        order_type = OrderType.RESALE
        seller_id = listing.seller_id
        ownership_id = listing.ownership_id
        amount = listing.price_stars
        commission_percent = platform.commission_percent
    else:
        if item_id is None:
            raise CheckoutError("Не указан предмет")
        item = lock_row(db, CollectionItem, CollectionItem.id == item_id).first()
        if item is None or item.status != "active":
            raise CheckoutError("Подарок недоступен")
        if item.minted_count >= item.edition_size:
            raise CheckoutError("Тираж распродан")
        amount = item.primary_price_stars
        commission_percent = 100  # the platform is the seller of primary mints

    if order_type == OrderType.RESALE:
        split = split_amount(amount, commission_percent)
    else:
        # Primary mints have no seller: the whole amount is platform revenue.
        split = Split(
            amount_stars=amount,
            commission_stars=amount,
            seller_stars=0,
            commission_percent=100,
            seller_percent=0,
        )

    order = Order(
        order_number=_order_number(),
        payload=secrets.token_urlsafe(24)[:48],
        buyer_id=user.id,
        seller_id=seller_id,
        item_id=item.id,
        ownership_id=ownership_id,
        listing_id=listing.id if listing else None,
        order_type=order_type.value,
        status=OrderStatus.PENDING_PAYMENT.value,
        amount_stars=amount,
        currency="XTR",
        commission_percent=split.commission_percent,
        commission_stars=split.commission_stars,
        seller_amount_stars=split.seller_stars if order_type == OrderType.RESALE else 0,
        expires_at=utcnow() + timedelta(minutes=30),
    )
    db.add(order)
    db.flush()

    payment = Payment(
        order_id=order.id,
        invoice_payload=order.payload,
        amount_stars=amount,
        currency="XTR",
        status=PaymentStatus.PENDING.value,
    )
    db.add(payment)
    db.flush()

    if listing:
        reserve_listing(db, listing, order, settings.listing_reservation_minutes)

    dev_simulated = not settings.bot_configured
    if not dev_simulated:
        try:
            payment.invoice_url = telegram_bot.create_invoice_link(
                title=item.name,
                description=f"{item.collection.name} · {item.rarity.upper()} · GIFT MARKET",
                payload=order.payload,
                amount_stars=amount,
                photo_url=item.image_url,
            )
        except telegram_bot.TelegramError as exc:
            db.rollback()
            logger.error("checkout.invoice_failed", extra={"user_id": user.id})
            raise CheckoutError(
                "Не удалось создать счёт Telegram. Попробуйте позже или обратитесь в поддержку."
            ) from exc
    elif not settings.dev_mode_enabled:
        # No bot token is only allowed in development (see config guards).
        db.rollback()
        raise CheckoutError("Платёжная система не настроена")

    notification = notifications.create_notification(
        db,
        user,
        type=NotificationType.PAYMENT_STATUS,
        title="Счёт создан",
        body=(
            f"{item.name} — {amount} Stars. Откройте счёт и оплатите его в Telegram, "
            "подарок придёт сразу после подтверждения платежа."
        ),
        payload={"order_id": order.id},
        telegram=False,
    )
    db.commit()
    db.refresh(order)
    db.refresh(payment)
    logger.info(
        "checkout.created",
        extra={"user_id": user.id, "order_id": order.id, "event": f"type={order_type.value}"},
    )
    return CheckoutResult(
        order=order, payment=payment, dev_simulated=dev_simulated, notifications=[notification.id]
    )


# ---------------------------------------------------------------------------
# Payment verification
# ---------------------------------------------------------------------------
def verify_and_record_payment(db: Session, payment_update: dict) -> tuple[Order, bool]:
    """Validate a Telegram ``successful_payment`` payload and persist it.

    Returns ``(order, newly_recorded)``. Repeated deliveries of the same
    update are idempotent because the charge id is unique per payment.
    """
    payload = str(payment_update.get("invoice_payload", ""))
    charge_id = str(payment_update.get("telegram_payment_charge_id", ""))
    provider_charge_id = str(payment_update.get("provider_payment_charge_id", ""))
    currency = str(payment_update.get("currency", ""))
    total_amount = int(payment_update.get("total_amount", 0))

    if not payload or not charge_id:
        raise FraudError("Payment update is missing payload or charge id")

    payment = db.scalar(select(Payment).where(Payment.invoice_payload == payload))
    if payment is None:
        raise FraudError("Unknown invoice payload")
    order = lock_row(db, Order, Order.id == payment.order_id).first()
    if order is None:  # pragma: no cover - FK guarantees this
        raise FraudError("Order for payment is missing")

    duplicate = db.scalar(
        select(Payment).where(
            Payment.telegram_payment_charge_id == charge_id, Payment.id != payment.id
        )
    )
    if duplicate is not None:
        raise FraudError("Charge id already used by another payment")

    if payment.status == PaymentStatus.SUCCEEDED.value:
        if payment.telegram_payment_charge_id not in {None, charge_id}:
            raise FraudError("Payment already completed with a different charge")
        return order, False

    if currency != order.currency or currency != "XTR":
        raise FraudError("Currency mismatch")
    if total_amount != order.amount_stars or total_amount != payment.amount_stars:
        raise FraudError("Amount mismatch: paid amount does not match the order")

    now = utcnow()
    payment.status = PaymentStatus.SUCCEEDED.value
    payment.telegram_payment_charge_id = charge_id
    payment.provider_payment_charge_id = provider_charge_id or None
    payment.paid_at = now
    payment.is_test = bool(payment_update.get("is_test", False))
    payment.raw_update = json.dumps(payment_update, ensure_ascii=False)[:20000]
    order.paid_at = now
    if order.status == OrderStatus.PENDING_PAYMENT.value:
        order.status = OrderStatus.PAID.value
    elif order.status in {OrderStatus.EXPIRED.value, OrderStatus.CANCELLED.value}:
        # Paid too late: keep the money recorded, fulfilment will refund it.
        order.status = OrderStatus.PAID.value
        order.failure_reason = "Оплата поступила после истечения заказа"
    db.flush()
    logger.info("payment.recorded", extra={"order_id": order.id, "user_id": order.buyer_id})
    return order, True


def approve_pre_checkout(db: Session, query: dict) -> tuple[bool, str]:
    """Validate a ``pre_checkout_query``. Never trusts client-supplied amounts."""
    payload = str(query.get("invoice_payload", ""))
    payment = db.scalar(select(Payment).where(Payment.invoice_payload == payload))
    if payment is None:
        return False, "Счёт не найден"
    order = db.get(Order, payment.order_id)
    if order is None:
        return False, "Заказ не найден"
    if order.status != OrderStatus.PENDING_PAYMENT.value:
        return False, "Заказ уже оплачен или отменён"
    if payment.status != PaymentStatus.PENDING.value:
        return False, "Счёт уже использован"
    if int(query.get("total_amount", 0)) != order.amount_stars:
        return False, "Сумма счёта не совпадает с заказом"
    if str(query.get("currency", "")) != order.currency:
        return False, "Валюта счёта не совпадает с заказом"

    if order.order_type == OrderType.RESALE.value and order.listing_id:
        listing = db.get(MarketplaceListing, order.listing_id)
        if listing is None or listing.status not in {
            ListingStatus.RESERVED.value,
            ListingStatus.ACTIVE.value,
        }:
            return False, "Подарок уже продан"
        if listing.reserved_order_id not in {None, order.id}:
            return False, "Подарок уже покупает другой пользователь"
    elif order.order_type == OrderType.PRIMARY.value:
        item = db.get(CollectionItem, order.item_id)
        if item is None or item.status != "active" or item.minted_count >= item.edition_size:
            return False, "Тираж распродан"

    if order.expires_at and order.expires_at < utcnow():
        return False, "Счёт истёк, создайте новый"
    return True, ""


# ---------------------------------------------------------------------------
# Fulfilment
# ---------------------------------------------------------------------------
def fulfill_paid_order(db: Session, order: Order) -> FulfillResult:
    """Transfer ownership + settle the ledger for a verified payment."""
    order = lock_row(db, Order, Order.id == order.id).first()
    assert order is not None
    if order.status == OrderStatus.FULFILLED.value:
        return FulfillResult(order=order)
    if order.status not in {OrderStatus.PAID.value, OrderStatus.REFUND_PENDING.value}:
        raise DeliveryError("Заказ не оплачен")

    buyer = db.get(User, order.buyer_id)
    if buyer is None:
        raise DeliveryError("Покупатель не найден")
    if buyer.is_blocked:
        raise DeliveryError("Аккаунт покупателя заблокирован")

    notification_ids: list[int] = []
    platform = get_platform_settings(db)
    hold_until = ledger.hold_deadline(platform.hold_hours) if order.seller_id else None

    try:
        if order.order_type == OrderType.RESALE.value and order.listing_id:
            listing = lock_row(db, MarketplaceListing, MarketplaceListing.id == order.listing_id).first()
            if listing is None:
                raise DeliveryError("Объявление удалено")
            if listing.reserved_order_id not in {None, order.id}:
                raise DeliveryError("Подарок уже покупает другой пользователь")
            if listing.status not in {
                ListingStatus.RESERVED.value,
                ListingStatus.ACTIVE.value,
            }:
                raise DeliveryError("Подарок больше не продаётся")
            ownership = lock_row(db, GiftOwnership, GiftOwnership.id == listing.ownership_id).first()
            if ownership is None:
                raise DeliveryError("Предмет не найден")
            if ownership.owner_id != listing.seller_id:
                raise DeliveryError("Владелец предмета изменился")
            if ownership.status != OwnershipStatus.OWNED.value:
                raise DeliveryError("Предмет недоступен")

            ownership_service.transfer_resale(db, ownership=ownership, order=order)
            listing.status = ListingStatus.SOLD.value
            listing.sold_order_id = order.id
            listing.sold_at = utcnow()
            listing.reserved_order_id = None
            listing.reserved_until = None
            order.ownership_id = ownership.id
        else:
            item = lock_row(db, CollectionItem, CollectionItem.id == order.item_id).first()
            if item is None:
                raise DeliveryError("Подарок не найден")
            ownership = ownership_service.mint_primary(db, item=item, buyer=buyer, order=order)
            order.ownership_id = ownership.id
    except ownership_service.OwnershipError as exc:
        raise DeliveryError(str(exc)) from exc

    ledger.credit_sale(db, order)

    order.status = OrderStatus.FULFILLED.value
    order.fulfilled_at = utcnow()
    order.hold_until = hold_until
    order.failure_reason = ""

    # Price history for the specific instance and the gift template.
    db.add(
        PriceHistory(
            item_id=order.item_id,
            ownership_id=order.ownership_id,
            listing_id=order.listing_id,
            scope=PriceHistoryScope.OWNERSHIP.value,
            event=PriceEvent.SOLD.value,
            price_stars=order.amount_stars,
        )
    )

    notification_ids.append(
        notifications.create_notification(
            db,
            buyer,
            type=NotificationType.PURCHASE,
            title="Покупка завершена",
            body=f"{order.item.name} теперь в вашей коллекции. Номер заказа {order.order_number}.",
            payload={"order_id": order.id},
        ).id
    )
    if order.seller_id:
        seller = db.get(User, order.seller_id)
        if seller:
            notification_ids.append(
                notifications.create_notification(
                    db,
                    seller,
                    type=NotificationType.SALE,
                    title="Ваш подарок продан",
                    body=(
                        f"{order.item.name} продан за {order.amount_stars} Stars. "
                        f"Ваш доход: {order.seller_amount_stars} Stars после комиссии "
                        f"{order.commission_stars} Stars."
                    ),
                    payload={"order_id": order.id},
                ).id
            )
            notification_ids.append(
                notifications.create_notification(
                    db,
                    seller,
                    type=NotificationType.SELLER_CREDIT,
                    title="Начисление на внутренний баланс",
                    body=(
                        f"{order.seller_amount_stars} Stars зачислены в ожидающие. "
                        f"Средства станут доступны после истечения периода удержания "
                        f"({platform.hold_hours:g} ч)."
                    ),
                    payload={"order_id": order.id},
                ).id
            )
    db.flush()
    logger.info("order.fulfilled", extra={"order_id": order.id, "user_id": order.buyer_id})
    return FulfillResult(order=order, notifications=notification_ids)


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
def refund_order(
    db: Session,
    order: Order,
    *,
    reason: str,
    requested_by_user_id: int | None = None,
) -> Refund:
    """Refund a paid order through Telegram's ``refundStarPayment``.

    Only unfulfilled orders can be refunded automatically; a fulfilled order
    needs manual handling (the item would have to be returned first).
    """
    order = lock_row(db, Order, Order.id == order.id).first()
    assert order is not None
    if order.status in {OrderStatus.REFUNDED.value}:
        existing = db.scalar(
            select(Refund)
            .where(Refund.order_id == order.id, Refund.status == RefundStatus.COMPLETED.value)
            .order_by(Refund.id.desc())
        )
        if existing:
            return existing
    if order.status == OrderStatus.FULFILLED.value:
        raise CheckoutError("Заказ уже исполнен: возврат возможен только вручную через поддержку")

    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None or payment.status != PaymentStatus.SUCCEEDED.value:
        raise CheckoutError("Нет подтверждённого платежа для возврата")
    if not payment.telegram_payment_charge_id:
        raise CheckoutError("Не найден идентификатор платежа Telegram")

    already = db.scalar(
        select(Refund).where(
            Refund.order_id == order.id,
            Refund.status.in_([RefundStatus.REQUESTED.value, RefundStatus.PROCESSING.value]),
        )
    )
    if already:
        return already

    refund = Refund(
        order_id=order.id,
        payment_id=payment.id,
        amount_stars=order.amount_stars,
        status=RefundStatus.PROCESSING.value,
        reason=reason[:500],
        requested_by_user_id=requested_by_user_id,
    )
    db.add(refund)
    db.flush()

    try:
        telegram_bot.refund_stars_payment(
            order.buyer.telegram_id, payment.telegram_payment_charge_id
        )
    except telegram_bot.TelegramError as exc:
        refund.status = RefundStatus.FAILED.value
        refund.error = str(exc)[:1000]
        order.status = OrderStatus.REFUND_PENDING.value
        order.failure_reason = f"Автовозврат не удался: {exc}. Нужен ручной возврат."
        db.commit()
        logger.error("refund.failed", extra={"order_id": order.id})
        return refund

    refund.status = RefundStatus.COMPLETED.value
    refund.completed_at = utcnow()
    payment.status = PaymentStatus.REFUNDED.value
    order.status = OrderStatus.REFUNDED.value
    order.failure_reason = reason[:500]
    telegram_id = order.buyer.telegram_id
    ledger.debit_refund(db, order, refund_id=refund.id, reason=reason)
    notifications.create_notification(
        db,
        order.buyer,
        type=NotificationType.PAYMENT_STATUS,
        title="Платёж возвращён",
        body=(
            f"{order.amount_stars} Stars возвращены на ваш счёт Telegram за заказ "
            f"{order.order_number}. Причина: {reason}."
        ),
        payload={"order_id": order.id},
    )
    db.commit()
    logger.warning(
        "refund.completed",
        extra={"order_id": order.id, "user_id": order.buyer_id, "event": f"charge={telegram_id}"},
    )
    return refund


def retry_pending_refunds(db: Session) -> int:
    """Retry refunds that failed earlier (called by the cleanup worker)."""
    orders = db.scalars(
        select(Order).where(Order.status == OrderStatus.REFUND_PENDING.value).limit(20)
    ).all()
    attempted = 0
    for order in orders:
        try:
            refund_order(db, order, reason=order.failure_reason or "Повторный возврат")
            attempted += 1
        except CheckoutError:
            continue
        except Exception:  # pragma: no cover - defensive
            db.rollback()
            logger.exception("refund.retry_failed")
    return attempted


def mark_order_delivery_failed(db: Session, order: Order, error: str) -> FulfillResult:
    """Paid order that cannot be delivered: refund and notify the buyer."""
    db.rollback()
    order = db.get(Order, order.id)
    assert order is not None
    try:
        refund = refund_order(db, order, reason=f"Товар недоступен: {error}")
    except CheckoutError as exc:
        logger.error("order.refund_not_possible", extra={"order_id": order.id})
        order = db.get(Order, order.id)
        order.status = OrderStatus.REFUND_PENDING.value
        order.failure_reason = f"{error}; возврат требует ручной обработки: {exc}"
        db.commit()
        return FulfillResult(order=order)
    order = db.get(Order, order.id)
    return FulfillResult(order=order, refund=refund)
