"""Marketplace actions: listings, checkout, orders, offers, reviews, reports."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.enums import (
    ListingStatus,
    NotificationType,
    OrderStatus,
    OwnershipStatus,
    ReportTargetType,
)
from app.core.logging import get_logger
from app.core.rate_limit import CHECKOUT_LIMIT, WRITE_LIMIT
from app.db.session import get_db
from app.models import (
    CollectionItem,
    GiftOwnership,
    MarketplaceListing,
    Offer,
    Order,
    Review,
    User,
)
from app.schemas.catalog import (
    ListingCreate,
    ListingCreated,
    ListingPublic,
    ListingUpdate,
    OfferCreate,
    OfferPublic,
    ReportCreate,
    ReviewCreate,
    ReviewPublic,
)
from app.schemas.common import Page
from app.schemas.orders import DevPayRequest, InvoiceRequest, InvoiceResponse, OrderDetail, OrderPublic
from app.services import marketplace, notifications, orders as order_service
from app.services.payments import PaymentOutcome, process_successful_payment
from app.services.presenters import (
    listing_public,
    order_detail,
    order_public,
    user_short,
)
from app.services.platform import get_platform_settings
from app.services.pricing import split_amount

logger = get_logger(__name__)
router = APIRouter(tags=["marketplace"])


def _checkout_error(exc: Exception) -> HTTPException:
    if isinstance(exc, marketplace.ListingError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/listings",
    response_model=ListingCreated,
    status_code=201,
    dependencies=[Depends(WRITE_LIMIT)],
)
def create_listing(
    payload: ListingCreate,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListingCreated:
    try:
        listing = marketplace.create_listing(
            db, user=user, ownership_id=payload.ownership_id, price_stars=payload.price_stars
        )
    except marketplace.ListingError as exc:
        db.rollback()
        raise _checkout_error(exc) from exc
    notification = notifications.create_notification(
        db,
        user,
        type=NotificationType.LISTING_CREATED,
        title="Объявление опубликовано",
        body=(
            f"{listing.ownership.item.name} выставлен за {listing.price_stars} Stars. "
            f"При продаже вы получите {split_amount(listing.price_stars, get_platform_settings(db).commission_percent).seller_stars} Stars."
        ),
        payload={"listing_id": listing.id},
    )
    db.commit()
    db.refresh(listing)
    background.add_task(notifications.deliver, notification.id)
    split = split_amount(listing.price_stars, get_platform_settings(db).commission_percent)
    return ListingCreated(
        listing=listing_public(listing),
        commission_percent=split.commission_percent,
        seller_receives_stars=split.seller_stars,
    )


@router.patch("/listings/{listing_id}", response_model=ListingPublic, dependencies=[Depends(WRITE_LIMIT)])
def update_listing(
    listing_id: int,
    payload: ListingUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListingPublic:
    try:
        listing = marketplace.update_listing(
            db, user=user, listing_id=listing_id, price_stars=payload.price_stars
        )
    except marketplace.ListingError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(listing)
    return listing_public(listing)


@router.delete("/listings/{listing_id}", dependencies=[Depends(WRITE_LIMIT)])
def cancel_listing(
    listing_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        listing = marketplace.cancel_listing(db, user=user, listing_id=listing_id)
    except marketplace.ListingError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    notification = notifications.create_notification(
        db,
        user,
        type=NotificationType.LISTING_CANCELLED,
        title="Объявление снято",
        body=f"{listing.ownership.item.name} больше не продаётся на маркете.",
        payload={"listing_id": listing.id},
        telegram=False,
    )
    db.commit()
    background.add_task(notifications.deliver, notification.id)
    return {"ok": True, "listing_id": listing_id}


@router.get("/listings/{listing_id}", response_model=ListingPublic)
def get_listing(listing_id: int, db: Session = Depends(get_db)) -> ListingPublic:
    listing = db.scalar(
        select(MarketplaceListing)
        .where(MarketplaceListing.id == listing_id)
        .options(
            joinedload(MarketplaceListing.ownership).joinedload(GiftOwnership.item),
            joinedload(MarketplaceListing.seller),
        )
    )
    if listing is None:
        raise HTTPException(404, "Объявление не найдено")
    return listing_public(listing)


@router.post(
    "/checkout/invoice",
    response_model=InvoiceResponse,
    dependencies=[Depends(CHECKOUT_LIMIT)],
)
def create_invoice(
    payload: InvoiceRequest,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    try:
        result = order_service.create_checkout(
            db, user=user, listing_id=payload.listing_id, item_id=payload.item_id
        )
    except order_service.CheckoutError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    for notification_id in result.notifications:
        background.add_task(notifications.deliver, notification_id)
    return InvoiceResponse(
        order_id=result.order.id,
        order_number=result.order.order_number,
        amount_stars=result.order.amount_stars,
        status=result.order.status,
        invoice_url=result.payment.invoice_url,
        expires_at=result.order.expires_at,
        commission_stars=result.order.commission_stars,
        seller_amount_stars=result.order.seller_amount_stars,
        item_name=result.order.item.name,
        dev_simulated=result.dev_simulated,
    )


@router.post("/checkout/dev-pay", response_model=dict, dependencies=[Depends(CHECKOUT_LIMIT)])
def dev_pay(
    payload: DevPayRequest,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Local development only: emulate a verified Telegram payment."""
    if not settings.dev_mode_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    order = db.get(Order, payload.order_id)
    if order is None or order.buyer_id != user.id:
        raise HTTPException(404, "Заказ не найден")
    if order.status != OrderStatus.PENDING_PAYMENT.value:
        raise HTTPException(409, f"Заказ в статусе {order.status}")
    outcome: PaymentOutcome = process_successful_payment(
        db,
        {
            "invoice_payload": order.payload,
            "currency": "XTR",
            "total_amount": order.amount_stars,
            "telegram_payment_charge_id": f"dev-{order.id}-{secrets.token_hex(6)}",
            "provider_payment_charge_id": f"dev-provider-{order.id}",
            "is_test": True,
        },
    )
    for notification_id in outcome.notifications:
        background.add_task(notifications.deliver, notification_id)
    return {
        "order_id": outcome.order_id,
        "status": outcome.status,
        "refunded": outcome.refunded,
        "already_processed": outcome.already_processed,
        "error": outcome.error,
    }


REVIEWED_STATUSES = OrderStatus.FULFILLED.value


def _reviewed_order_ids(db: Session, user_id: int) -> set[int]:
    rows = db.scalars(select(Review.order_id).where(Review.author_id == user_id)).all()
    return set(rows)


@router.get("/orders", response_model=Page[OrderPublic])
def my_orders(
    role: str = Query(default="buyer", pattern="^(buyer|seller)$"),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=200),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[OrderPublic]:
    condition = Order.buyer_id == user.id if role == "buyer" else Order.seller_id == user.id
    base = select(Order).where(condition)
    if status_filter:
        base = base.where(Order.status == status_filter)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(
            joinedload(Order.item),
            joinedload(Order.seller),
            joinedload(Order.buyer),
            joinedload(Order.ownership),
        )
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    reviewed = _reviewed_order_ids(db, user.id)
    return Page.build(
        [order_public(row, reviewed=row.id in reviewed) for row in rows], int(total), page, page_size
    )


@router.get("/orders/{order_id}", response_model=OrderDetail)
def order_detail_view(
    order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OrderDetail:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            joinedload(Order.item),
            joinedload(Order.seller),
            joinedload(Order.buyer),
            joinedload(Order.ownership),
            joinedload(Order.payment),
        )
    )
    if order is None or user.id not in {order.buyer_id, order.seller_id}:
        raise HTTPException(404, "Заказ не найден")
    reviewed = order.id in _reviewed_order_ids(db, user.id)
    return order_detail(order, reviewed=reviewed)


@router.get("/orders/{order_id}/receipt")
def order_receipt(
    order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    order = db.get(Order, order_id)
    if order is None or user.id not in {order.buyer_id, order.seller_id}:
        raise HTTPException(404, "Заказ не найден")
    payment = order.payment
    return {
        "order_number": order.order_number,
        "amount_stars": order.amount_stars,
        "currency": order.currency,
        "status": order.status,
        "paid_at": order.paid_at,
        "telegram_payment_charge_id": payment.telegram_payment_charge_id if payment else None,
        "commission_stars": order.commission_stars,
        "seller_amount_stars": order.seller_amount_stars,
    }


@router.post("/orders/{order_id}/refund", dependencies=[Depends(WRITE_LIMIT)])
def request_refund(
    order_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Buyer-initiated refund for a paid order that has not been fulfilled."""
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != user.id:
        raise HTTPException(404, "Заказ не найден")
    if order.status not in {OrderStatus.PAID.value, OrderStatus.REFUND_PENDING.value}:
        raise HTTPException(
            409,
            "Автоматический возврат доступен только для оплаченных, но не исполненных заказов. "
            "Для остальных случаев обратитесь в поддержку.",
        )
    try:
        refund = order_service.refund_order(
            db, order, reason="Возврат по запросу покупателя", requested_by_user_id=user.id
        )
    except order_service.CheckoutError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return {"refund_id": refund.id, "status": refund.status, "amount_stars": refund.amount_stars}


@router.post("/reviews", response_model=ReviewPublic, status_code=201, dependencies=[Depends(WRITE_LIMIT)])
def create_review(
    payload: ReviewCreate,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewPublic:
    order = db.get(Order, payload.order_id)
    if order is None or order.buyer_id != user.id:
        raise HTTPException(404, "Заказ не найден")
    if order.status != REVIEWED_STATUSES:
        raise HTTPException(409, "Отзыв можно оставить только после получения подарка")
    if not order.seller_id:
        raise HTTPException(409, "Для первичных покупок отзыв не требуется")
    existing = db.scalar(select(Review).where(Review.order_id == order.id))
    if existing:
        raise HTTPException(409, "Отзыв по этому заказу уже оставлен")
    review = Review(
        order_id=order.id,
        author_id=user.id,
        seller_id=order.seller_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    seller = db.get(User, order.seller_id)
    if seller:
        seller.rating_count += 1
        seller.rating_sum += payload.rating
        notification = notifications.create_notification(
            db,
            seller,
            type=NotificationType.SYSTEM,
            title="Новый отзыв",
            body=f"{user.display_name} оценил сделку на {payload.rating}/5.",
            payload={"order_id": order.id},
            telegram=False,
        )
    else:  # pragma: no cover
        notification = None
    db.commit()
    db.refresh(review)
    if notification:
        background.add_task(notifications.deliver, notification.id)
    return ReviewPublic(
        id=review.id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        author=user_short(user),
    )


@router.post("/offers", response_model=OfferPublic, status_code=201, dependencies=[Depends(WRITE_LIMIT)])
def create_offer(
    payload: OfferCreate,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferPublic:
    platform = get_platform_settings(db)
    if not platform.maintenance_mode:
        pass
    ownership = db.scalar(
        select(GiftOwnership)
        .where(GiftOwnership.id == payload.ownership_id)
        .options(joinedload(GiftOwnership.item))
    )
    if ownership is None or ownership.status != OwnershipStatus.OWNED.value:
        raise HTTPException(404, "Предмет не найден")
    if ownership.owner_id == user.id:
        raise HTTPException(400, "Нельзя предложить цену за собственный предмет")
    if not ownership.item.is_tradeable:
        raise HTTPException(409, "Этот предмет нельзя перепродать")
    seller = db.get(User, ownership.owner_id)
    if seller is None or seller.is_blocked:
        raise HTTPException(409, "Владелец недоступен")
    if not seller.allow_offers:
        raise HTTPException(403, "Владелец отключил предложения")
    if payload.price_stars < platform.min_listing_price:
        raise HTTPException(400, f"Минимальная цена — {platform.min_listing_price} Stars")
    active = db.scalar(
        select(MarketplaceListing).where(
            MarketplaceListing.ownership_id == ownership.id,
            MarketplaceListing.status.in_(
                [ListingStatus.ACTIVE.value, ListingStatus.RESERVED.value]
            ),
        )
    )
    if active:
        raise HTTPException(409, "Предмет уже продаётся, купите его напрямую")
    existing = db.scalar(
        select(Offer).where(
            Offer.ownership_id == ownership.id,
            Offer.buyer_id == user.id,
            Offer.status == "pending",
        )
    )
    if existing:
        existing.price_stars = payload.price_stars
        existing.message = payload.message
        offer = existing
    else:
        offer = Offer(
            ownership_id=ownership.id,
            buyer_id=user.id,
            seller_id=ownership.owner_id,
            price_stars=payload.price_stars,
            message=payload.message,
        )
        db.add(offer)
        db.flush()
    notification = notifications.create_notification(
        db,
        seller,
        type=NotificationType.OFFER,
        title="Новое предложение",
        body=(
            f"{user.display_name} предлагает {payload.price_stars} Stars за "
            f"{ownership.item.name}. Откройте профиль, чтобы принять или отклонить."
        ),
        payload={"offer_id": offer.id},
    )
    db.commit()
    db.refresh(offer)
    background.add_task(notifications.deliver, notification.id)
    return OfferPublic(
        id=offer.id,
        ownership_id=offer.ownership_id,
        price_stars=offer.price_stars,
        message=offer.message,
        status=offer.status,
        created_at=offer.created_at,
        buyer=user_short(user),
        item_name=ownership.item.name,
        image_url=ownership.item.image_url,
    )


@router.post("/offers/{offer_id}/accept", dependencies=[Depends(WRITE_LIMIT)])
def accept_offer(
    offer_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    offer = db.scalar(
        select(Offer)
        .where(Offer.id == offer_id)
        .options(joinedload(Offer.ownership).joinedload(GiftOwnership.item))
    )
    if offer is None or offer.seller_id != user.id:
        raise HTTPException(404, "Предложение не найдено")
    if offer.status != "pending":
        raise HTTPException(409, "Предложение уже обработано")
    try:
        listing = marketplace.create_listing(
            db, user=user, ownership_id=offer.ownership_id, price_stars=offer.price_stars
        )
    except marketplace.ListingError as exc:
        db.rollback()
        raise HTTPException(409, detail=str(exc)) from exc
    offer.status = "accepted"
    buyer = db.get(User, offer.buyer_id)
    notification = None
    if buyer:
        notification = notifications.create_notification(
            db,
            buyer,
            type=NotificationType.OFFER,
            title="Предложение принято",
            body=(
                f"Продавец принял вашу цену {offer.price_stars} Stars за {offer.ownership.item.name}. "
                "Оплатите заказ, чтобы получить подарок."
            ),
            payload={"listing_id": listing.id, "offer_id": offer.id},
        )
    db.commit()
    if notification:
        background.add_task(notifications.deliver, notification.id)
    return {"ok": True, "listing_id": listing.id, "price_stars": listing.price_stars}


@router.post("/offers/{offer_id}/decline", dependencies=[Depends(WRITE_LIMIT)])
def decline_offer(
    offer_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    offer = db.scalar(select(Offer).where(Offer.id == offer_id))
    if offer is None or offer.seller_id != user.id:
        raise HTTPException(404, "Предложение не найдено")
    if offer.status != "pending":
        raise HTTPException(409, "Предложение уже обработано")
    offer.status = "declined"
    buyer = db.get(User, offer.buyer_id)
    notification = None
    if buyer:
        notification = notifications.create_notification(
            db,
            buyer,
            type=NotificationType.OFFER,
            title="Предложение отклонено",
            body=f"Владелец отклонил вашу цену {offer.price_stars} Stars.",
            payload={"offer_id": offer.id},
            telegram=False,
        )
    db.commit()
    if notification:
        background.add_task(notifications.deliver, notification.id)
    return {"ok": True}


@router.post("/reports", dependencies=[Depends(WRITE_LIMIT)])
def create_report(
    payload: ReportCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    target_type = ReportTargetType(payload.target_type)
    exists = {
        ReportTargetType.GIFT: db.get(CollectionItem, payload.target_id),
        ReportTargetType.LISTING: db.get(MarketplaceListing, payload.target_id),
        ReportTargetType.USER: db.get(User, payload.target_id),
        ReportTargetType.ORDER: db.get(Order, payload.target_id),
    }[target_type]
    if exists is None:
        raise HTTPException(404, "Объект жалобы не найден")
    from app.models import Report

    report = Report(
        reporter_id=user.id,
        target_type=target_type.value,
        target_id=payload.target_id,
        reason=payload.reason,
        details=payload.details,
    )
    db.add(report)
    db.commit()
    logger.info("report.created", extra={"user_id": user.id, "event": target_type.value})
    return {"ok": True, "report_id": report.id}
