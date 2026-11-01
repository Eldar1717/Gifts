"""Payment processing pipeline shared by the webhook and the dev simulator."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import NotificationType, OrderStatus, PaymentStatus
from app.core.logging import get_logger
from app.models import Order
from app.services import notifications, telegram_bot
from app.services.orders import (
    DeliveryError,
    FraudError,
    fulfill_paid_order,
    mark_order_delivery_failed,
    verify_and_record_payment,
)

logger = get_logger(__name__)


@dataclass
class PaymentOutcome:
    order_id: int | None
    status: str
    already_processed: bool = False
    refunded: bool = False
    error: str = ""
    notifications: list[int] = field(default_factory=list)


TERMINAL_STATUSES = {
    OrderStatus.FULFILLED.value,
    OrderStatus.REFUNDED.value,
    OrderStatus.REFUND_PENDING.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.FAILED.value,
}


def process_successful_payment(db: Session, payment_update: dict) -> PaymentOutcome:
    """Idempotent pipeline: verify -> record -> fulfil -> (refund on failure)."""
    try:
        order, newly_recorded = verify_and_record_payment(db, payment_update)
    except FraudError as exc:
        db.rollback()
        logger.error("payment.fraud_rejected", extra={"event": str(exc)})
        return PaymentOutcome(order_id=None, status="rejected", error=str(exc))

    db.commit()

    order = db.get(Order, order.id)
    assert order is not None
    if order.status in TERMINAL_STATUSES:
        if not newly_recorded:
            logger.info("payment.duplicate_ignored", extra={"order_id": order.id})
            return PaymentOutcome(order.id, order.status, already_processed=True)
        if order.status == OrderStatus.REFUND_PENDING.value:
            return PaymentOutcome(order.id, order.status, refunded=True)

    try:
        result = fulfill_paid_order(db, order)
        db.commit()
        logger.info("payment.fulfilled", extra={"order_id": order.id})
        return PaymentOutcome(
            order.id,
            OrderStatus.FULFILLED.value,
            notifications=result.notifications,
        )
    except DeliveryError as exc:
        db.rollback()
        logger.warning("payment.delivery_failed", extra={"order_id": order.id, "event": str(exc)})
        result = mark_order_delivery_failed(db, order, str(exc))
        return PaymentOutcome(
            result.order.id,
            result.order.status,
            refunded=result.refund is not None,
            error=str(exc),
            notifications=result.notifications,
        )
    except Exception as exc:  # pragma: no cover - unexpected, keep money safe
        db.rollback()
        logger.exception("payment.fulfilment_crashed", extra={"order_id": order.id})
        failed = db.get(Order, order.id)
        if failed:
            failed.status = OrderStatus.REFUND_PENDING.value
            failed.failure_reason = f"Внутренняя ошибка исполнения: {exc}"
            db.commit()
        return PaymentOutcome(order.id, OrderStatus.REFUND_PENDING.value, error=str(exc))


def simulate_payment(db: Session, order: Order, *, charge_id: str) -> PaymentOutcome:
    """DEV ONLY: emulate a Telegram successful_payment update."""
    payment = order.payment
    if payment is None:
        return PaymentOutcome(order.id, order.status, error="Payment not found")
    return process_successful_payment(
        db,
        {
            "invoice_payload": payment.invoice_payload,
            "currency": "XTR",
            "total_amount": payment.amount_stars,
            "telegram_payment_charge_id": charge_id,
            "provider_payment_charge_id": f"dev-{charge_id}",
            "is_test": True,
        },
    )


def notify_outcome(db: Session, outcome: PaymentOutcome) -> None:
    """Best-effort Telegram delivery of notifications created during the flow."""
    if outcome.notifications:
        notifications.deliver_many(outcome.notifications)


def refund_message(order: Order) -> str:
    return (
        f"Возврат {order.amount_stars} Stars по заказу {order.order_number} "
        f"({order.item.name}) выполнен через Telegram."
    )


# Re-exported so routers do not need to import several modules
__all__ = [
    "PaymentOutcome",
    "TelegramError",
    "notify_outcome",
    "process_successful_payment",
    "simulate_payment",
    "telegram_bot",
    "PaymentStatus",
    "NotificationType",
]

from app.services.telegram_bot import TelegramError  # noqa: E402  (public re-export)
