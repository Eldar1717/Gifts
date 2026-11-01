"""Double-entry style internal ledger for seller balances.

Rules:
* There is no bank account, no crypto wallet and no automatic withdrawal.
* Every movement is an immutable ``transactions`` row with a unique
  idempotency key, so retried webhooks can never double-credit a seller.
* ``seller_balances`` is a cached projection of those rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import LedgerBucket, TransactionType
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models import Order, PayoutRequest, SellerBalance, Transaction, User

logger = get_logger(__name__)


class LedgerError(Exception):
    pass


def get_or_create_balance(db: Session, user_id: int) -> SellerBalance:
    balance = db.scalar(select(SellerBalance).where(SellerBalance.user_id == user_id))
    if balance is None:
        balance = SellerBalance(user_id=user_id)
        db.add(balance)
        db.flush()
    return balance


def _existing(db: Session, key: str) -> Transaction | None:
    return db.scalar(select(Transaction).where(Transaction.idempotency_key == key))


def record(
    db: Session,
    *,
    key: str,
    type: TransactionType,
    bucket: LedgerBucket,
    amount_stars: int,
    user_id: int | None = None,
    order_id: int | None = None,
    payout_id: int | None = None,
    refund_id: int | None = None,
    description: str = "",
    balance_after: int | None = None,
) -> Transaction | None:
    """Append a ledger row once. Returns ``None`` when the key already exists."""
    if amount_stars == 0:
        raise LedgerError("Ledger amount must be non-zero")
    if _existing(db, key):
        logger.info("ledger.duplicate_skipped", extra={"event": key})
        return None
    row = Transaction(
        user_id=user_id,
        order_id=order_id,
        payout_id=payout_id,
        refund_id=refund_id,
        type=type.value,
        bucket=bucket.value,
        amount_stars=amount_stars,
        balance_after=balance_after,
        description=description[:280],
        idempotency_key=key,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:  # concurrent worker inserted the same key first
        db.rollback()
        logger.warning("ledger.integrity_race", extra={"event": key})
        return None
    return row


def credit_sale(db: Session, order: Order) -> None:
    """Credit seller income to *pending* and record platform commission.

    Primary sales (minted by the platform) have no seller: the whole amount is
    platform revenue.
    """
    if order.seller_amount_stars > 0 and order.seller_id:
        balance = get_or_create_balance(db, order.seller_id)
        balance.pending_stars += order.seller_amount_stars
        balance.lifetime_stars += order.seller_amount_stars
        balance.version += 1
        record(
            db,
            key=f"sale:{order.id}",
            type=TransactionType.SALE_CREDIT,
            bucket=LedgerBucket.PENDING,
            amount_stars=order.seller_amount_stars,
            user_id=order.seller_id,
            order_id=order.id,
            description=f"Продажа #{order.order_number}: {order.amount_stars} Stars, комиссия {order.commission_stars}",
            balance_after=balance.pending_stars,
        )

    # Platform commission (for resale) or full primary proceeds.
    platform_amount = order.commission_stars if order.seller_id else order.amount_stars
    if platform_amount > 0:
        record(
            db,
            key=f"commission:{order.id}",
            type=TransactionType.COMMISSION,
            bucket=LedgerBucket.PLATFORM,
            amount_stars=platform_amount,
            order_id=order.id,
            description=(
                f"Комиссия платформы {order.commission_percent}% по заказу #{order.order_number}"
                if order.seller_id
                else f"Первичная продажа #{order.order_number}"
            ),
        )


def release_pending(db: Session, order: Order) -> None:
    """Move seller income from pending to available once the hold expires."""
    if not order.seller_id or order.seller_amount_stars <= 0:
        return
    key = f"release:{order.id}"
    if _existing(db, key):
        return
    balance = get_or_create_balance(db, order.seller_id)
    amount = min(order.seller_amount_stars, balance.pending_stars)
    if amount <= 0:
        # Nothing left pending (e.g. already clawed back by a refund).
        record(
            db,
            key=key,
            type=TransactionType.SETTLEMENT,
            bucket=LedgerBucket.AVAILABLE,
            amount_stars=1,
            user_id=order.seller_id,
            order_id=order.id,
            description="Расчётный период завершён без начислений",
        )
        return
    balance.pending_stars -= amount
    balance.available_stars += amount
    balance.version += 1
    record(
        db,
        key=key,
        type=TransactionType.SETTLEMENT,
        bucket=LedgerBucket.AVAILABLE,
        amount_stars=amount,
        user_id=order.seller_id,
        order_id=order.id,
        description=f"Средства по заказу #{order.order_number} доступны к выплате",
        balance_after=balance.available_stars,
    )


def debit_refund(db: Session, order: Order, *, refund_id: int, reason: str) -> None:
    """Reverse a seller credit after a refund.

    Takes money from pending first, then available. If the seller no longer
    holds the funds (already withdrawn), the platform absorbs the difference
    and records it explicitly instead of creating a negative balance.
    """
    if not order.seller_id or order.seller_amount_stars <= 0:
        return
    key = f"refund:{refund_id}"
    if _existing(db, key):
        return
    balance = get_or_create_balance(db, order.seller_id)
    remaining = order.seller_amount_stars
    from_pending = min(balance.pending_stars, remaining)
    balance.pending_stars -= from_pending
    remaining -= from_pending
    from_available = min(balance.available_stars, remaining)
    balance.available_stars -= from_available
    remaining -= from_available
    applied = from_pending + from_available
    absorbed = remaining
    balance.lifetime_stars = max(0, balance.lifetime_stars - applied)
    balance.version += 1
    record(
        db,
        key=key,
        type=TransactionType.REFUND_DEBIT,
        bucket=LedgerBucket.PENDING if from_pending else LedgerBucket.AVAILABLE,
        amount_stars=-(applied or 1),
        user_id=order.seller_id,
        order_id=order.id,
        refund_id=refund_id,
        description=f"Отмена начисления по возврату заказа #{order.order_number}: {reason}"[:280],
        balance_after=balance.pending_stars,
    )
    if absorbed:
        record(
            db,
            key=f"refund-platform:{refund_id}",
            type=TransactionType.REFUND_DEBIT,
            bucket=LedgerBucket.EXTERNAL,
            amount_stars=-absorbed,
            order_id=order.id,
            refund_id=refund_id,
            description=f"Платформа покрыла {absorbed} Stars по возврату #{order.order_number}",
        )
    if order.commission_stars > 0:
        record(
            db,
            key=f"refund-commission:{refund_id}",
            type=TransactionType.REFUND_DEBIT,
            bucket=LedgerBucket.PLATFORM,
            amount_stars=-order.commission_stars,
            order_id=order.id,
            refund_id=refund_id,
            description=f"Возврат комиссии по заказу #{order.order_number}",
        )


def settle_due_holds(db: Session, *, now: datetime | None = None) -> int:
    """Release every fulfilled order whose hold window has passed."""
    moment = now or utcnow()
    orders = db.scalars(
        select(Order).where(
            Order.status == "fulfilled",
            Order.hold_until.is_not(None),
            Order.hold_until <= moment,
            Order.seller_id.is_not(None),
            Order.seller_amount_stars > 0,
        )
    ).all()
    settled = 0
    for order in orders:
        key = f"release:{order.id}"
        if _existing(db, key):
            continue
        release_pending(db, order)
        order.hold_until = None
        settled += 1
    return settled


def hold_deadline(hours: float, start: datetime | None = None) -> datetime:
    return (start or utcnow()) + timedelta(hours=hours)


def request_payout(
    db: Session, user: User, amount_stars: int, method: str, destination: str, minimum: int = 1
) -> PayoutRequest:
    if amount_stars < minimum:
        raise LedgerError(f"Минимальная сумма выплаты — {minimum} Stars")
    balance = get_or_create_balance(db, user.id)
    if balance.available_stars < amount_stars:
        raise LedgerError("Недостаточно доступных средств")
    balance.available_stars -= amount_stars
    balance.version += 1
    payout = PayoutRequest(
        user_id=user.id,
        amount_stars=amount_stars,
        method=method,
        destination=destination,
        status="requested",
    )
    db.add(payout)
    db.flush()
    record(
        db,
        key=f"payout-request:{payout.id}",
        type=TransactionType.PAYOUT_REQUEST,
        bucket=LedgerBucket.PAYOUT,
        amount_stars=-amount_stars,
        user_id=user.id,
        payout_id=payout.id,
        description=f"Заявка на выплату #{payout.id}",
        balance_after=balance.available_stars,
    )
    return payout


def decide_payout(
    db: Session,
    payout: PayoutRequest,
    *,
    status: str,
    admin_note: str,
    external_reference: str,
) -> None:
    balance = get_or_create_balance(db, payout.user_id)
    if payout.status in {"paid", "rejected"}:
        raise LedgerError("Заявка уже обработана")
    if status == "rejected":
        balance.available_stars += payout.amount_stars
        balance.version += 1
        record(
            db,
            key=f"payout-reversal:{payout.id}",
            type=TransactionType.PAYOUT_REVERSAL,
            bucket=LedgerBucket.AVAILABLE,
            amount_stars=payout.amount_stars,
            user_id=payout.user_id,
            payout_id=payout.id,
            description=f"Заявка на выплату #{payout.id} отклонена: {admin_note}"[:280],
            balance_after=balance.available_stars,
        )
        payout.status = "rejected"
    elif status == "approved":
        payout.status = "approved"
    elif status == "paid":
        if payout.status != "approved":
            raise LedgerError("Перед отметкой об оплате заявку нужно подтвердить")
        balance.withdrawn_stars += payout.amount_stars
        balance.version += 1
        record(
            db,
            key=f"payout-paid:{payout.id}",
            type=TransactionType.PAYOUT_PAID,
            bucket=LedgerBucket.EXTERNAL,
            amount_stars=-payout.amount_stars,
            user_id=payout.user_id,
            payout_id=payout.id,
            description=f"Выплата #{payout.id} произведена: {external_reference}"[:280],
        )
        payout.status = "paid"
        payout.paid_at = utcnow()
    else:  # pragma: no cover - guarded by schema
        raise LedgerError("Unknown payout status")
    payout.admin_note = admin_note
    payout.external_reference = external_reference
    payout.decided_at = utcnow()


def admin_adjustment(
    db: Session, *, user_id: int, amount_stars: int, reason: str, admin_id: int
) -> SellerBalance:
    balance = get_or_create_balance(db, user_id)
    if amount_stars > 0:
        balance.available_stars += amount_stars
        bucket = LedgerBucket.AVAILABLE
    else:
        take = min(balance.available_stars, -amount_stars)
        balance.available_stars -= take
        bucket = LedgerBucket.AVAILABLE
    balance.version += 1
    record(
        db,
        key=f"admin-adjust:{admin_id}:{user_id}:{utcnow().isoformat()}:{amount_stars}",
        type=TransactionType.ADMIN_ADJUSTMENT,
        bucket=bucket,
        amount_stars=amount_stars,
        user_id=user_id,
        description=f"Корректировка администратором #{admin_id}: {reason}"[:280],
        balance_after=balance.available_stars,
    )
    return balance
