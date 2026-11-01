"""Authenticated account endpoints: profile, collection, balance, favorites."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import admin_role, get_current_user
from app.core.enums import ListingStatus, NotificationType, OrderStatus
from app.core.rate_limit import READ_LIMIT, WRITE_LIMIT
from app.db.session import get_db
from app.models import (
    Favorite,
    GiftOwnership,
    MarketplaceListing,
    Notification,
    Offer,
    Order,
    PayoutRequest,
    Transaction,
    User,
)
from app.schemas.catalog import (
    FavoriteToggle,
    MarketCard,
    OfferPublic,
    OwnershipCard,
    OwnershipDetail,
)
from app.schemas.common import Page
from app.schemas.users import (
    BalancePublic,
    MeResponse,
    NotificationPublic,
    PayoutCreate,
    PayoutPublic,
    PrivacySettings,
    ProfileSettingsUpdate,
    StatsPublic,
    TonWalletUpdate,
    TransactionPublic,
)
from app.services import catalog as catalog_service, ledger, notifications, ton
from app.services.platform import get_platform_settings
from app.services.presenters import market_card_from_listing, market_card_primary, user_public

router = APIRouter(tags=["account"], dependencies=[Depends(READ_LIMIT)])


def _stats(db: Session, user: User) -> StatsPublic:
    gifts_owned = db.scalar(
        select(func.count())
        .select_from(GiftOwnership)
        .where(GiftOwnership.owner_id == user.id, GiftOwnership.status == "owned")
    ) or 0
    listings_active = db.scalar(
        select(func.count())
        .select_from(MarketplaceListing)
        .where(
            MarketplaceListing.seller_id == user.id,
            MarketplaceListing.status == ListingStatus.ACTIVE.value,
        )
    ) or 0
    gross_sales = db.scalar(
        select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
            Order.seller_id == user.id, Order.status == OrderStatus.FULFILLED.value
        )
    ) or 0
    gross_purchases = db.scalar(
        select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
            Order.buyer_id == user.id, Order.status == OrderStatus.FULFILLED.value
        )
    ) or 0
    balance = ledger.get_or_create_balance(db, user.id)
    return StatsPublic(
        gifts_owned=int(gifts_owned),
        listings_active=int(listings_active),
        sales_count=user.sales_count,
        purchases_count=user.purchases_count,
        gross_sales_stars=int(gross_sales),
        gross_purchases_stars=int(gross_purchases),
        lifetime_seller_stars=balance.lifetime_stars,
        rating_count=user.rating_count,
        rating=user.rating,
    )


def _balance_payload(db: Session, user: User) -> BalancePublic:
    platform = get_platform_settings(db)
    balance = ledger.get_or_create_balance(db, user.id)
    db.commit()
    return BalancePublic(
        pending_stars=balance.pending_stars,
        available_stars=balance.available_stars,
        withdrawn_stars=balance.withdrawn_stars,
        lifetime_stars=balance.lifetime_stars,
        hold_hours=platform.hold_hours,
        can_request_payout=balance.available_stars >= platform.min_payout_stars,
        payout_note=platform.payout_note,
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    role = admin_role(user, db)
    platform = get_platform_settings(db)
    return MeResponse(
        user=user_public(user),
        is_admin=bool(user.is_admin and role),
        admin_role=role,
        settings=PrivacySettings(
            show_collection=user.show_collection,
            allow_offers=user.allow_offers,
            notify_sales=user.notify_sales,
            notify_market=user.notify_market,
        ),
        ton_address=user.ton_address,
        stats=_stats(db, user),
        balance=BalancePublic(
            pending_stars=(balance := ledger.get_or_create_balance(db, user.id)).pending_stars,
            available_stars=balance.available_stars,
            withdrawn_stars=balance.withdrawn_stars,
            lifetime_stars=balance.lifetime_stars,
            hold_hours=platform.hold_hours,
            can_request_payout=balance.available_stars >= platform.min_payout_stars,
            payout_note=platform.payout_note,
        ),
        unread_notifications=notifications.unread_count(db, user.id),
    )


@router.patch("/me/settings", response_model=PrivacySettings, dependencies=[Depends(WRITE_LIMIT)])
def update_settings(
    payload: ProfileSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PrivacySettings:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(user, field, value)
    db.commit()
    return PrivacySettings(
        show_collection=user.show_collection,
        allow_offers=user.allow_offers,
        notify_sales=user.notify_sales,
        notify_market=user.notify_market,
    )


@router.post("/me/ton", dependencies=[Depends(WRITE_LIMIT)])
def bind_ton(
    payload: TonWalletUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Bind a public TON address. Ownership of the wallet is **not** proven here."""
    if not payload.address:
        user.ton_address = ""
        user.ton_address_verified_at = None
        db.commit()
        return {"address": "", "verified": False}
    try:
        info = ton.verify_wallet(payload.address)
    except ton.TonError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    user.ton_address = payload.address
    db.commit()
    return {
        "address": user.ton_address,
        "exists_on_chain": True,
        "balance_nanoton": info.get("balance_nanoton", 0),
        "note": "Адрес сохранён. Подпись владения кошельком не проверялась.",
    }


@router.get("/me/balance", response_model=BalancePublic)
def my_balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BalancePublic:
    return _balance_payload(db, user)


@router.get("/me/transactions", response_model=Page[TransactionPublic])
def my_transactions(
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[TransactionPublic]:
    base = select(Transaction).where(Transaction.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page.build(
        [TransactionPublic.model_validate(row) for row in rows], int(total), page, page_size
    )


def _ownership_cards(db: Session, user: User) -> list[OwnershipCard]:
    ownerships = db.scalars(
        select(GiftOwnership)
        .where(GiftOwnership.owner_id == user.id)
        .options(joinedload(GiftOwnership.item).joinedload(catalog_service.CollectionItem.collection))
        .order_by(GiftOwnership.acquired_at.desc(), GiftOwnership.id.desc())
    ).unique().all()
    listing_map: dict[int, MarketplaceListing] = {}
    if ownerships:
        listings = db.scalars(
            select(MarketplaceListing)
            .where(
                MarketplaceListing.ownership_id.in_([o.id for o in ownerships]),
                MarketplaceListing.status.in_(
                    [ListingStatus.ACTIVE.value, ListingStatus.RESERVED.value]
                ),
            )
            .options(joinedload(MarketplaceListing.seller))
        ).unique().all()
        listing_map = {listing.ownership_id: listing for listing in listings}
    return [
        catalog_service_and_listing_card(db, ownership, listing_map.get(ownership.id))
        for ownership in ownerships
    ]


def catalog_service_and_listing_card(db: Session, ownership: GiftOwnership, listing) -> OwnershipCard:
    from app.services.presenters import ownership_card

    card = ownership_card(ownership, listing)
    cheapest = catalog_service.cheapest_listing_price(db, ownership.item_id)
    card.estimated_value_stars = cheapest or ownership.item.primary_price_stars
    return card


@router.get("/me/collection", response_model=list[OwnershipCard])
def my_collection(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[OwnershipCard]:
    return _ownership_cards(db, user)


@router.get("/me/collection/{ownership_id}", response_model=OwnershipDetail)
def my_ownership(
    ownership_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OwnershipDetail:
    ownership = db.scalar(
        select(GiftOwnership)
        .where(GiftOwnership.id == ownership_id, GiftOwnership.owner_id == user.id)
        .options(joinedload(GiftOwnership.item).joinedload(catalog_service.CollectionItem.collection))
    )
    if ownership is None:
        raise HTTPException(404, "Предмет не найден в коллекции")
    listing = db.scalar(
        select(MarketplaceListing)
        .where(
            MarketplaceListing.ownership_id == ownership.id,
            MarketplaceListing.status.in_(
                [ListingStatus.ACTIVE.value, ListingStatus.RESERVED.value]
            ),
        )
        .options(joinedload(MarketplaceListing.seller))
    )
    card = catalog_service_and_listing_card(db, ownership, listing)
    history = catalog_service.owners_history(db, ownership.id)
    return OwnershipDetail(
        **card.model_dump(),
        history=history,
        price_history=catalog_service.price_history(db, ownership.item_id),
    )


@router.get("/me/listings")
def my_listings(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    rows = db.scalars(
        select(MarketplaceListing)
        .where(MarketplaceListing.seller_id == user.id)
        .options(
            joinedload(MarketplaceListing.ownership).joinedload(GiftOwnership.item),
            joinedload(MarketplaceListing.seller),
        )
        .order_by(MarketplaceListing.listed_at.desc())
        .limit(100)
    ).unique().all()
    from app.services.presenters import listing_public

    return [listing_public(row).model_dump() for row in rows]


@router.get("/favorites", response_model=list[MarketCard])
def favorites(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[MarketCard]:
    item_ids = db.scalars(
        select(Favorite.item_id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
        .limit(200)
    ).all()
    if not item_ids:
        return []
    items = db.scalars(
        select(catalog_service.CollectionItem)
        .where(catalog_service.CollectionItem.id.in_(item_ids))
        .options(joinedload(catalog_service.CollectionItem.collection))
    ).unique().all()
    cards: list[MarketCard] = []
    for item in items:
        listing = catalog_service.active_listing_for_item(db, item.id)
        cards.append(
            market_card_from_listing(listing) if listing else market_card_primary(item)
        )
    return cards


@router.post("/favorites/{item_id}", response_model=FavoriteToggle, dependencies=[Depends(WRITE_LIMIT)])
def toggle_favorite(
    item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> FavoriteToggle:
    item = db.get(catalog_service.CollectionItem, item_id)
    if item is None or item.status == "draft":
        raise HTTPException(404, "Подарок не найден")
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.item_id == item_id)
    )
    if existing:
        db.delete(existing)
        favorite = False
    else:
        db.add(Favorite(user_id=user.id, item_id=item_id))
        favorite = True
    db.commit()
    return FavoriteToggle(item_id=item_id, favorite=favorite)


@router.get("/notifications", response_model=Page[NotificationPublic])
def my_notifications(
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1, le=200),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[NotificationPublic]:
    base = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        base = base.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page.build(
        [NotificationPublic.model_validate(row) for row in rows], int(total), page, page_size
    )


@router.post("/notifications/read", dependencies=[Depends(WRITE_LIMIT)])
def read_notifications(
    ids: list[int] | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    count = notifications.mark_read(db, user.id, ids or None)
    db.commit()
    return {"updated": count, "unread": notifications.unread_count(db, user.id)}


@router.post("/me/payouts", response_model=PayoutPublic, dependencies=[Depends(WRITE_LIMIT)])
def create_payout(
    payload: PayoutCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PayoutPublic:
    platform = get_platform_settings(db)
    try:
        payout = ledger.request_payout(
            db,
            user,
            payload.amount_stars,
            payload.method.value,
            payload.destination,
            minimum=platform.min_payout_stars,
        )
    except ledger.LedgerError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notifications.create_notification(
        db,
        user,
        type=NotificationType.PAYOUT,
        title="Заявка на выплату создана",
        body=(
            f"{payload.amount_stars} Stars зарезервированы. Выплата выполняется вручную "
            "после проверки, вы получите уведомление о решении."
        ),
        payload={"payout_id": payout.id},
        telegram=False,
    )
    db.commit()
    db.refresh(payout)
    return PayoutPublic.model_validate(payout)


@router.get("/me/payouts", response_model=list[PayoutPublic])
def my_payouts(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PayoutPublic]:
    rows = db.scalars(
        select(PayoutRequest)
        .where(PayoutRequest.user_id == user.id)
        .order_by(PayoutRequest.created_at.desc())
        .limit(50)
    ).all()
    return [PayoutPublic.model_validate(row) for row in rows]


@router.get("/me/offers", response_model=list[OfferPublic])
def my_offers(
    direction: str = Query(default="incoming", pattern="^(incoming|outgoing)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OfferPublic]:
    condition = Offer.seller_id == user.id if direction == "incoming" else Offer.buyer_id == user.id
    rows = db.scalars(
        select(Offer)
        .where(condition)
        .options(
            joinedload(Offer.buyer),
        )
        .order_by(Offer.created_at.desc())
        .limit(100)
    ).unique().all()
    ownership_ids = {row.ownership_id for row in rows}
    ownerships = {}
    if ownership_ids:
        ownerships = {
            o.id: o
            for o in db.scalars(
                select(GiftOwnership)
                .where(GiftOwnership.id.in_(ownership_ids))
                .options(joinedload(GiftOwnership.item))
            ).unique().all()
        }
    result: list[OfferPublic] = []
    for row in rows:
        ownership = ownerships.get(row.ownership_id)
        result.append(
            OfferPublic(
                id=row.id,
                ownership_id=row.ownership_id,
                price_stars=row.price_stars,
                message=row.message,
                status=row.status,
                created_at=row.created_at,
                buyer=catalog_service_user_short(row.buyer),
                item_name=ownership.item.name if ownership else "",
                image_url=ownership.item.image_url if ownership else "",
            )
        )
    return result


def catalog_service_user_short(user: User):
    from app.services.presenters import user_short

    return user_short(user)
