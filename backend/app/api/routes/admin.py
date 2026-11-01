"""Protected admin panel API. Every mutating action is written to the audit log."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_admin, require_superadmin
from app.core.config import settings
from app.core.enums import (
    AdminRole,
    LedgerBucket,
    ListingStatus,
    NotificationType,
    OrderStatus,
    ReportStatus,
    TransactionType,
)
from app.core.rate_limit import WRITE_LIMIT
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    AdminUser,
    AuditLog,
    Category,
    Collection,
    CollectionItem,
    GiftOwnership,
    MarketplaceListing,
    Notification,
    Order,
    PayoutRequest,
    Report,
    Review,
    SellerBalance,
    Transaction,
    User,
)
from app.schemas.admin import (
    AdminBalanceAdjustment,
    AdminItemRow,
    AdminListingRow,
    AdminOrderRow,
    AdminOverview,
    AdminSettingsPublic,
    AdminUserRow,
    AdminUserUpdate,
    AuditLogRow,
    CategoryCreate,
    CategoryUpdate,
    CollectionCreate,
    CollectionUpdate,
    GiftGrant,
    ItemCreate,
    ItemUpdate,
    PayoutDecision,
    PayoutRow,
    ReportResolve,
    ReportRow,
    SettingsUpdate,
)
from app.schemas.common import Message, Page
from app.schemas.users import UserShort
from app.services import audit, ledger, telegram_bot, ton
from app.services.catalog import collection_stats
from app.services.ownership import OwnershipError, grant_item
from app.services.platform import get_platform_settings
from app.services.presenters import collection_public, item_card, user_short

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _short(user: User | None) -> UserShort | None:
    return user_short(user)


def _overview(db: Session) -> AdminOverview:
    now = utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    total_volume = db.scalar(
        select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
            Order.status == OrderStatus.FULFILLED.value
        )
    ) or 0
    platform_revenue = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_stars), 0)).where(
            Transaction.bucket == LedgerBucket.PLATFORM.value
        )
    ) or 0
    seller_credits = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_stars), 0)).where(
            Transaction.type == TransactionType.SALE_CREDIT.value
        )
    ) or 0
    seller_pending = db.scalar(select(func.coalesce(func.sum(SellerBalance.pending_stars), 0))) or 0
    seller_available = db.scalar(select(func.coalesce(func.sum(SellerBalance.available_stars), 0))) or 0
    pending_payouts = db.scalar(
        select(func.coalesce(func.sum(PayoutRequest.amount_stars), 0)).where(
            PayoutRequest.status.in_(["requested", "approved"])
        )
    ) or 0
    pending_payout_count = db.scalar(
        select(func.count(PayoutRequest.id)).where(PayoutRequest.status.in_(["requested", "approved"]))
    ) or 0

    orders_count = db.scalar(select(func.count(Order.id))) or 0
    paid_count = db.scalar(
        select(func.count(Order.id)).where(
            Order.status.in_(
                [OrderStatus.PAID.value, OrderStatus.FULFILLED.value, OrderStatus.REFUND_PENDING.value]
            )
        )
    ) or 0
    fulfilled_count = db.scalar(
        select(func.count(Order.id)).where(Order.status == OrderStatus.FULFILLED.value)
    ) or 0
    active_users_7d = db.scalar(
        select(func.count(func.distinct(Order.buyer_id))).where(Order.created_at >= since_7d)
    ) or 0
    active_users_30d = db.scalar(
        select(func.count(func.distinct(Order.buyer_id))).where(Order.created_at >= since_30d)
    ) or 0

    top_rows = db.execute(
        select(Order.item_id, func.count(Order.id).label("count"), func.sum(Order.amount_stars))
        .where(Order.status == OrderStatus.FULFILLED.value)
        .group_by(Order.item_id)
        .order_by(func.count(Order.id).desc())
        .limit(5)
    ).all()
    items = {
        item.id: item
        for item in db.scalars(
            select(CollectionItem).where(CollectionItem.id.in_([row[0] for row in top_rows]))
        ).unique().all()
    } if top_rows else {}
    top_gifts = [
        {
            "id": row[0],
            "name": items[row[0]].name if row[0] in items else f"#{row[0]}",
            "sales": row[1],
            "volume_stars": int(row[2] or 0),
        }
        for row in top_rows
    ]

    series: list[dict] = []
    for offset in range(13, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        revenue = db.scalar(
            select(func.coalesce(func.sum(Transaction.amount_stars), 0)).where(
                Transaction.bucket == LedgerBucket.PLATFORM.value,
                Transaction.created_at >= day_start,
                Transaction.created_at < day_end,
            )
        ) or 0
        volume = db.scalar(
            select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
                Order.status == OrderStatus.FULFILLED.value,
                Order.fulfilled_at >= day_start,
                Order.fulfilled_at < day_end,
            )
        ) or 0
        orders_day = db.scalar(
            select(func.count(Order.id)).where(
                Order.status == OrderStatus.FULFILLED.value,
                Order.fulfilled_at >= day_start,
                Order.fulfilled_at < day_end,
            )
        ) or 0
        series.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "revenue_stars": int(revenue),
                "volume_stars": int(volume),
                "orders": int(orders_day),
            }
        )

    recent = db.scalars(
        select(Order)
        .options(joinedload(Order.item), joinedload(Order.buyer), joinedload(Order.seller))
        .order_by(Order.created_at.desc())
        .limit(8)
    ).unique().all()

    return AdminOverview(
        total_volume_stars=int(total_volume),
        platform_revenue_stars=int(platform_revenue),
        seller_credits_stars=int(seller_credits),
        orders_count=int(orders_count),
        orders_paid_count=int(paid_count),
        orders_fulfilled_count=int(fulfilled_count),
        active_users_7d=int(active_users_7d),
        active_users_30d=int(active_users_30d),
        users_total=int(db.scalar(select(func.count(User.id))) or 0),
        active_listings=int(
            db.scalar(
                select(func.count(MarketplaceListing.id)).where(
                    MarketplaceListing.status == ListingStatus.ACTIVE.value
                )
            )
            or 0
        ),
        collections_total=int(db.scalar(select(func.count(Collection.id))) or 0),
        gifts_minted=int(db.scalar(select(func.count(GiftOwnership.id))) or 0),
        pending_payouts_stars=int(pending_payouts),
        pending_payout_requests=int(pending_payout_count),
        open_reports=int(
            db.scalar(
                select(func.count(Report.id)).where(
                    Report.status.in_([ReportStatus.OPEN.value, ReportStatus.REVIEWING.value])
                )
            )
            or 0
        ),
        seller_pending_stars=int(seller_pending),
        seller_available_stars=int(seller_available),
        revenue_24h_stars=int(
            db.scalar(
                select(func.coalesce(func.sum(Transaction.amount_stars), 0)).where(
                    Transaction.bucket == LedgerBucket.PLATFORM.value,
                    Transaction.created_at >= since_24h,
                )
            )
            or 0
        ),
        volume_24h_stars=int(
            db.scalar(
                select(func.coalesce(func.sum(Order.amount_stars), 0)).where(
                    Order.status == OrderStatus.FULFILLED.value,
                    Order.fulfilled_at >= since_24h,
                )
            )
            or 0
        ),
        orders_24h=int(
            db.scalar(select(func.count(Order.id)).where(Order.created_at >= since_24h)) or 0
        ),
        top_gifts=top_gifts,
        revenue_series=series,
        recent_orders=[
            {
                "id": order.id,
                "order_number": order.order_number,
                "item_name": order.item.name,
                "amount_stars": order.amount_stars,
                "status": order.status,
                "buyer": user_short(order.buyer),
                "created_at": order.created_at,
            }
            for order in recent
        ],
    )


@router.get("/overview", response_model=AdminOverview)
def overview(db: Session = Depends(get_db)) -> AdminOverview:
    return _overview(db)


@router.get("/stats", response_model=AdminOverview)
def stats(db: Session = Depends(get_db)) -> AdminOverview:
    return _overview(db)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@router.get("/users", response_model=Page[AdminUserRow])
def list_users(
    q: str | None = Query(default=None, max_length=80),
    blocked: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[AdminUserRow]:
    base = select(User)
    if q:
        like = f"%{q.strip()}%"
        conditions = [User.username.ilike(like), User.first_name.ilike(like), User.last_name.ilike(like)]
        if q.strip().isdigit():
            conditions.append(User.telegram_id == int(q.strip()))
        base = base.where(or_(*conditions))
    if blocked is not None:
        base = base.where(User.is_blocked.is_(blocked))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    user_ids = [row.id for row in rows]
    balances = {
        b.user_id: b
        for b in db.scalars(select(SellerBalance).where(SellerBalance.user_id.in_(user_ids))).all()
    } if user_ids else {}
    counts = dict(
        db.execute(
            select(GiftOwnership.owner_id, func.count(GiftOwnership.id))
            .where(GiftOwnership.owner_id.in_(user_ids))
            .group_by(GiftOwnership.owner_id)
        ).all()
    ) if user_ids else {}
    admins = {
        a.user_id: a
        for a in db.scalars(select(AdminUser).where(AdminUser.user_id.in_(user_ids))).all()
    } if user_ids else {}
    items = [
        AdminUserRow(
            id=row.id,
            telegram_id=row.telegram_id,
            username=row.username,
            display_name=row.display_name,
            photo_url=row.photo_url,
            is_admin=row.is_admin,
            is_blocked=row.is_blocked,
            admin_role=admins[row.id].role if row.id in admins and admins[row.id].is_active else None,
            sales_count=row.sales_count,
            purchases_count=row.purchases_count,
            gifts_owned=int(counts.get(row.id, 0)),
            available_stars=balances[row.id].available_stars if row.id in balances else 0,
            pending_stars=balances[row.id].pending_stars if row.id in balances else 0,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]
    return Page.build(items, int(total), page, page_size)


@router.patch("/users/{user_id}", response_model=Message, dependencies=[Depends(WRITE_LIMIT)])
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Message:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    before = {"is_blocked": user.is_blocked, "is_admin": user.is_admin}
    if payload.is_blocked is not None:
        if user.id == admin.id and payload.is_blocked:
            raise HTTPException(400, "Нельзя заблокировать собственный аккаунт")
        user.is_blocked = payload.is_blocked
        user.blocked_reason = payload.blocked_reason or "" if payload.is_blocked else ""
    if payload.is_admin is not None:
        admin_row = db.scalar(select(AdminUser).where(AdminUser.user_id == user.id))
        if payload.is_admin:
            role = (payload.admin_role or AdminRole.ADMIN).value
            if admin_row is None:
                admin_row = AdminUser(user_id=user.id, role=role, is_active=True)
                db.add(admin_row)
            else:
                admin_row.role = role
                admin_row.is_active = True
            user.is_admin = True
        else:
            if user.id == admin.id:
                raise HTTPException(400, "Нельзя снять права с себя")
            if admin_row:
                admin_row.is_active = False
            user.is_admin = False
    elif payload.admin_role and payload.is_admin is None:
        admin_row = db.scalar(select(AdminUser).where(AdminUser.user_id == user.id))
        if admin_row:
            admin_row.role = payload.admin_role.value
    db.flush()
    audit.log_action(
        db,
        admin=admin,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after={"is_blocked": user.is_blocked, "is_admin": user.is_admin},
        request=request,
    )
    db.commit()
    return Message(message="Пользователь обновлён")


@router.post(
    "/users/{user_id}/balance", response_model=Message, dependencies=[Depends(WRITE_LIMIT)]
)
def adjust_balance(
    user_id: int,
    payload: AdminBalanceAdjustment,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Message:
    if payload.user_id != user_id:
        raise HTTPException(400, "user_id в пути и теле запроса не совпадают")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    ledger.admin_adjustment(
        db, user_id=user_id, amount_stars=payload.amount_stars, reason=payload.reason, admin_id=admin.id
    )
    audit.log_action(
        db,
        admin=admin,
        action="balance.adjustment",
        entity_type="user",
        entity_id=user_id,
        after={"amount_stars": payload.amount_stars, "reason": payload.reason},
        request=request,
    )
    db.commit()
    return Message(message="Баланс скорректирован")


@router.post("/users/{user_id}/notify", response_model=Message, dependencies=[Depends(WRITE_LIMIT)])
def notify_user(
    user_id: int,
    background: BackgroundTasks,
    title: str = Query(min_length=1, max_length=120),
    body: str = Query(default="", max_length=1000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Message:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    notification = notifications_create(db, user, title, body)
    db.commit()
    background.add_task(notify_deliver, notification.id)
    return Message(message="Уведомление отправлено")


def notifications_create(db: Session, user: User, title: str, body: str):
    from app.services import notifications

    return notifications.create_notification(
        db, user, type=NotificationType.ADMIN, title=title, body=body
    )


def notify_deliver(notification_id: int) -> None:
    from app.services.notifications import deliver

    deliver(notification_id)


# ---------------------------------------------------------------------------
# Categories & collections
# ---------------------------------------------------------------------------
@router.get("/categories", response_model=list[dict])
def admin_categories(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()
    return [
        {
            "id": row.id,
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "emoji": row.emoji,
            "sort_order": row.sort_order,
            "is_active": row.is_active,
            "collections": int(
                db.scalar(select(func.count(Collection.id)).where(Collection.category_id == row.id)) or 0
            ),
        }
        for row in rows
    ]


@router.post("/categories", status_code=201, dependencies=[Depends(WRITE_LIMIT)])
def create_category(
    payload: CategoryCreate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    if db.scalar(select(Category).where(Category.slug == payload.slug)):
        raise HTTPException(409, "Категория с таким slug уже существует")
    category = Category(**payload.model_dump())
    db.add(category)
    audit.log_action(
        db, admin=admin, action="category.create", entity_type="category", after=payload.model_dump(), request=request
    )
    db.commit()
    return {"id": category.id}


@router.patch("/categories/{category_id}", dependencies=[Depends(WRITE_LIMIT)])
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Категория не найдена")
    data = payload.model_dump(exclude_unset=True)
    before = {key: getattr(category, key) for key in data}
    for key, value in data.items():
        setattr(category, key, value)
    audit.log_action(
        db,
        admin=admin,
        action="category.update",
        entity_type="category",
        entity_id=category.id,
        before=before,
        after=data,
        request=request,
    )
    db.commit()
    return {"ok": True}


@router.get("/collections", response_model=list[dict])
def admin_collections(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Collection).options(joinedload(Collection.category)).order_by(Collection.created_at.desc())
    ).unique().all()
    result = []
    for row in rows:
        items_count, sold, floor = collection_stats(db, row)
        payload = collection_public(
            row, items_count=items_count, items_sold=sold, floor=floor
        ).model_dump()
        payload["items_total"] = int(
            db.scalar(select(func.count(CollectionItem.id)).where(CollectionItem.collection_id == row.id)) or 0
        )
        result.append(payload)
    return result


@router.post("/collections", status_code=201, dependencies=[Depends(WRITE_LIMIT)])
def create_collection(
    payload: CollectionCreate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    if db.scalar(select(Collection).where(Collection.slug == payload.slug)):
        raise HTTPException(409, "Коллекция с таким slug уже существует")
    collection = Collection(**payload.model_dump())
    db.add(collection)
    db.flush()
    audit.log_action(
        db,
        admin=admin,
        action="collection.create",
        entity_type="collection",
        entity_id=collection.id,
        after=payload.model_dump(),
        request=request,
    )
    db.commit()
    return {"id": collection.id}


@router.patch("/collections/{collection_id}", dependencies=[Depends(WRITE_LIMIT)])
def update_collection(
    collection_id: int,
    payload: CollectionUpdate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(404, "Коллекция не найдена")
    data = payload.model_dump(exclude_unset=True)
    before = {key: getattr(collection, key) for key in data}
    for key, value in data.items():
        setattr(collection, key, value)
    audit.log_action(
        db,
        admin=admin,
        action="collection.update",
        entity_type="collection",
        entity_id=collection.id,
        before=before,
        after=data,
        request=request,
    )
    db.commit()
    return {"ok": True}


@router.post(
    "/collections/{collection_id}/verify-ton", dependencies=[Depends(WRITE_LIMIT)]
)
def verify_collection_ton(
    collection_id: int,
    request: Request,
    address: str = Query(min_length=3, max_length=80),
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(404, "Коллекция не найдена")
    try:
        ton.verify_collection_onchain(collection, address)
    except ton.TonError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audit.log_action(
        db,
        admin=admin,
        action="collection.verify_ton",
        entity_type="collection",
        entity_id=collection.id,
        after={"address": address},
        request=request,
    )
    db.commit()
    return {
        "ok": True,
        "address": address,
        "note": "Адрес существует в TON. Минт предметов подтверждается отдельно.",
    }


# ---------------------------------------------------------------------------
# Gifts (collection items)
# ---------------------------------------------------------------------------
@router.get("/items", response_model=Page[AdminItemRow])
def admin_items(
    q: str | None = Query(default=None, max_length=80),
    collection_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[AdminItemRow]:
    base = select(CollectionItem).join(CollectionItem.collection)
    if q:
        base = base.where(CollectionItem.name.ilike(f"%{q.strip()}%"))
    if collection_id:
        base = base.where(CollectionItem.collection_id == collection_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(CollectionItem.collection))
        .order_by(CollectionItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            AdminItemRow(
                item=item_card(row),
                collection_name=row.collection.name,
                minted_count=row.minted_count,
                edition_size=row.edition_size,
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.post("/items", status_code=201, dependencies=[Depends(WRITE_LIMIT)])
def create_item(
    payload: ItemCreate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    collection = db.get(Collection, payload.collection_id)
    if collection is None:
        raise HTTPException(404, "Коллекция не найдена")
    if db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == payload.collection_id,
            CollectionItem.name == payload.name,
        )
    ):
        raise HTTPException(409, "Подарок с таким названием уже есть в коллекции")
    item = CollectionItem(**payload.model_dump())
    db.add(item)
    db.flush()
    audit.log_action(
        db,
        admin=admin,
        action="item.create",
        entity_type="item",
        entity_id=item.id,
        after=payload.model_dump(),
        request=request,
    )
    db.commit()
    return {"id": item.id}


@router.patch("/items/{item_id}", dependencies=[Depends(WRITE_LIMIT)])
def update_item(
    item_id: int,
    payload: ItemUpdate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(CollectionItem, item_id)
    if item is None:
        raise HTTPException(404, "Подарок не найден")
    data = payload.model_dump(exclude_unset=True)
    before = {key: getattr(item, key) for key in data}
    for key, value in data.items():
        setattr(item, key, value)
    audit.log_action(
        db,
        admin=admin,
        action="item.update",
        entity_type="item",
        entity_id=item.id,
        before=before,
        after=data,
        request=request,
    )
    db.commit()
    return {"ok": True}


@router.post("/gifts/grant", response_model=Message, dependencies=[Depends(WRITE_LIMIT)])
def grant_gifts(
    payload: GiftGrant,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Message:
    user = db.get(User, payload.user_id)
    item = db.get(CollectionItem, payload.item_id)
    if user is None or item is None:
        raise HTTPException(404, "Пользователь или подарок не найден")
    granted = 0
    try:
        for _ in range(payload.quantity):
            grant_item(db, item=item, user=user, price=0, admin_id=admin.id)
            granted += 1
    except OwnershipError as exc:
        db.rollback()
        raise HTTPException(409, detail=str(exc)) from exc
    audit.log_action(
        db,
        admin=admin,
        action="gift.grant",
        entity_type="user",
        entity_id=user.id,
        after={"item_id": item.id, "quantity": granted, "reason": payload.reason},
        request=request,
    )
    db.commit()
    return Message(message=f"Выдано предметов: {granted}")


# ---------------------------------------------------------------------------
# Orders, listings, transactions, refunds
# ---------------------------------------------------------------------------
@router.get("/orders", response_model=Page[AdminOrderRow])
def admin_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[AdminOrderRow]:
    base = select(Order)
    if status_filter:
        base = base.where(Order.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(Order.order_number.ilike(like), Order.payload.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(Order.item), joinedload(Order.buyer), joinedload(Order.seller))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            AdminOrderRow(
                id=row.id,
                order_number=row.order_number,
                item_name=row.item.name,
                image_url=row.item.image_url,
                buyer=_short(row.buyer),
                seller=_short(row.seller),
                amount_stars=row.amount_stars,
                commission_stars=row.commission_stars,
                seller_amount_stars=row.seller_amount_stars,
                status=row.status,
                created_at=row.created_at,
                paid_at=row.paid_at,
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.post("/orders/{order_id}/refund", dependencies=[Depends(WRITE_LIMIT)])
def admin_refund_order(
    order_id: int,
    background: BackgroundTasks,
    request: Request,
    reason: str = Query(default="Возврат администратором", max_length=200),
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    from app.services import orders as order_service

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Заказ не найден")
    try:
        refund = order_service.refund_order(
            db, order, reason=reason, requested_by_user_id=admin.id
        )
    except order_service.CheckoutError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    for notification in db.scalars(
        select(Notification).where(
            Notification.user_id == order.buyer_id,
            Notification.type == NotificationType.PAYMENT_STATUS.value,
            Notification.is_read.is_(False),
        )
    ).all():
        background.add_task(notify_deliver, notification.id)
    audit.log_action(
        db,
        admin=admin,
        action="order.refund",
        entity_type="order",
        entity_id=order.id,
        after={"refund_id": refund.id, "status": refund.status},
        request=request,
    )
    db.commit()
    return {"refund_id": refund.id, "status": refund.status}


@router.get("/listings", response_model=Page[AdminListingRow])
def admin_listings(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[AdminListingRow]:
    base = select(MarketplaceListing)
    if status_filter:
        base = base.where(MarketplaceListing.status == status_filter)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(
            joinedload(MarketplaceListing.ownership).joinedload(GiftOwnership.item),
            joinedload(MarketplaceListing.seller),
        )
        .order_by(MarketplaceListing.listed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            AdminListingRow(
                id=row.id,
                item=item_card(row.ownership.item),
                seller=_short(row.seller),
                price_stars=row.price_stars,
                status=row.status,
                listed_at=row.listed_at,
                views=row.views,
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.post("/listings/{listing_id}/cancel", dependencies=[Depends(WRITE_LIMIT)])
def admin_cancel_listing(
    listing_id: int,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Message:
    listing = db.get(MarketplaceListing, listing_id)
    if listing is None:
        raise HTTPException(404, "Объявление не найдено")
    if listing.status == ListingStatus.RESERVED.value:
        raise HTTPException(409, "Объявление забронировано покупателем")
    listing.status = ListingStatus.CANCELLED.value
    audit.log_action(
        db,
        admin=admin,
        action="listing.cancel",
        entity_type="listing",
        entity_id=listing.id,
        request=request,
    )
    db.commit()
    return Message(message="Объявление снято")


@router.get("/transactions", response_model=Page[dict])
def admin_transactions(
    type_filter: str | None = Query(default=None, alias="type"),
    bucket: str | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[dict]:
    base = select(Transaction)
    if type_filter:
        base = base.where(Transaction.type == type_filter)
    if bucket:
        base = base.where(Transaction.bucket == bucket)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(Transaction.user))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            {
                "id": row.id,
                "type": row.type,
                "bucket": row.bucket,
                "amount_stars": row.amount_stars,
                "balance_after": row.balance_after,
                "description": row.description,
                "order_id": row.order_id,
                "user": _short(row.user),
                "created_at": row.created_at,
            }
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.get("/refunds", response_model=Page[dict])
def admin_refunds(
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[dict]:
    from app.models import Refund

    base = select(Refund)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Refund.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page.build(
        [
            {
                "id": row.id,
                "order_id": row.order_id,
                "amount_stars": row.amount_stars,
                "status": row.status,
                "reason": row.reason,
                "error": row.error,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------
@router.get("/payouts", response_model=Page[PayoutRow])
def admin_payouts(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[PayoutRow]:
    base = select(PayoutRequest)
    if status_filter:
        base = base.where(PayoutRequest.status == status_filter)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(PayoutRequest.user))
        .order_by(PayoutRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            PayoutRow(
                id=row.id,
                user=_short(row.user),
                amount_stars=row.amount_stars,
                method=row.method,
                destination=row.destination,
                status=row.status,
                admin_note=row.admin_note,
                external_reference=row.external_reference,
                created_at=row.created_at,
                decided_at=row.decided_at,
                paid_at=row.paid_at,
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.post("/payouts/{payout_id}", response_model=Message, dependencies=[Depends(WRITE_LIMIT)])
def decide_payout(
    payout_id: int,
    payload: PayoutDecision,
    request: Request,
    background: BackgroundTasks,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Message:
    payout = db.get(PayoutRequest, payout_id)
    if payout is None:
        raise HTTPException(404, "Заявка не найдена")
    try:
        ledger.decide_payout(
            db,
            payout,
            status=payload.status,
            admin_note=payload.admin_note,
            external_reference=payload.external_reference,
        )
    except ledger.LedgerError as exc:
        db.rollback()
        raise HTTPException(409, detail=str(exc)) from exc
    user = db.get(User, payout.user_id)
    notification = None
    if user:
        titles = {
            "approved": "Заявка на выплату подтверждена",
            "rejected": "Заявка на выплату отклонена",
            "paid": "Выплата произведена",
        }
        bodies = {
            "approved": f"Заявка #{payout.id} на {payout.amount_stars} Stars подтверждена и будет оплачена.",
            "rejected": f"Заявка #{payout.id} отклонена. Средства возвращены на доступный баланс. {payload.admin_note}",
            "paid": f"Выплата #{payout.id} на {payout.amount_stars} Stars отмечена как произведённая.",
        }
        notification = notifications_create(db, user, titles[payload.status], bodies[payload.status])
    audit.log_action(
        db,
        admin=admin,
        action=f"payout.{payload.status}",
        entity_type="payout",
        entity_id=payout.id,
        after=payload.model_dump(),
        request=request,
    )
    db.commit()
    if notification:
        background.add_task(notify_deliver, notification.id)
    return Message(message="Заявка обновлена")


# ---------------------------------------------------------------------------
# Reports, reviews, audit, settings
# ---------------------------------------------------------------------------
@router.get("/reports", response_model=Page[ReportRow])
def admin_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[ReportRow]:
    base = select(Report)
    if status_filter:
        base = base.where(Report.status == status_filter)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(Report.reporter))
        .order_by(Report.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            ReportRow(
                id=row.id,
                reporter=_short(row.reporter),
                target_type=row.target_type,
                target_id=row.target_id,
                reason=row.reason,
                details=row.details,
                status=row.status,
                resolution=row.resolution,
                created_at=row.created_at,
                resolved_at=row.resolved_at,
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.post("/reports/{report_id}", response_model=Message, dependencies=[Depends(WRITE_LIMIT)])
def resolve_report(
    report_id: int,
    payload: ReportResolve,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Message:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(404, "Жалоба не найдена")
    report.status = payload.status
    report.resolution = payload.resolution
    report.resolved_by_user_id = admin.id
    report.resolved_at = utcnow() if payload.status in {"resolved", "dismissed"} else None
    audit.log_action(
        db,
        admin=admin,
        action="report.resolve",
        entity_type="report",
        entity_id=report.id,
        after=payload.model_dump(),
        request=request,
    )
    db.commit()
    return Message(message="Жалоба обновлена")


@router.get("/reviews", response_model=Page[dict])
def admin_reviews(
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[dict]:
    base = select(Review)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(Review.author))
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            {
                "id": row.id,
                "rating": row.rating,
                "comment": row.comment,
                "author": _short(row.author),
                "seller_id": row.seller_id,
                "order_id": row.order_id,
                "is_hidden": row.is_hidden,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.post("/reviews/{review_id}/hide", response_model=Message, dependencies=[Depends(WRITE_LIMIT)])
def hide_review(
    review_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Message:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "Отзыв не найден")
    review.is_hidden = not review.is_hidden
    audit.log_action(
        db,
        admin=admin,
        action="review.hide" if review.is_hidden else "review.show",
        entity_type="review",
        entity_id=review.id,
        request=request,
    )
    db.commit()
    return Message(message="Отзыв обновлён")


@router.get("/audit-logs", response_model=Page[AuditLogRow])
def audit_logs(
    action: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1, le=500),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[AuditLogRow]:
    base = select(AuditLog)
    if action:
        base = base.where(AuditLog.action.ilike(f"%{action}%"))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(joinedload(AuditLog.admin))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return Page.build(
        [
            AuditLogRow(
                id=row.id,
                admin=_short(row.admin),
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                before=row.before,
                after=row.after,
                ip_address=row.ip_address,
                created_at=row.created_at,
            )
            for row in rows
        ],
        int(total),
        page,
        page_size,
    )


@router.get("/settings", response_model=AdminSettingsPublic)
def get_settings_view(db: Session = Depends(get_db)) -> AdminSettingsPublic:
    platform = get_platform_settings(db)
    updater = db.get(User, platform.updated_by_user_id) if platform.updated_by_user_id else None
    return AdminSettingsPublic(
        commission_percent=platform.commission_percent,
        min_listing_price=platform.min_listing_price,
        max_listing_price=platform.max_listing_price,
        hold_hours=platform.hold_hours,
        maintenance_mode=platform.maintenance_mode,
        maintenance_message=platform.maintenance_message,
        max_active_listings=platform.max_active_listings,
        min_payout_stars=platform.min_payout_stars,
        payout_note=platform.payout_note,
        terms_url=platform.terms_url,
        updated_at=platform.updated_at,
        updated_by=_short(updater),
    )


@router.patch("/settings", response_model=AdminSettingsPublic, dependencies=[Depends(WRITE_LIMIT)])
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> AdminSettingsPublic:
    platform = get_platform_settings(db)
    data = payload.model_dump(exclude_unset=True)
    before = {key: getattr(platform, key) for key in data}
    for key, value in data.items():
        if value is not None:
            setattr(platform, key, value)
    platform.updated_by_user_id = admin.id
    platform.updated_at = utcnow()
    if platform.max_listing_price < platform.min_listing_price:
        raise HTTPException(400, "Максимальная цена не может быть ниже минимальной")
    audit.log_action(
        db,
        admin=admin,
        action="settings.update",
        entity_type="platform_settings",
        entity_id=1,
        before=before,
        after=data,
        request=request,
    )
    db.commit()
    return get_settings_view(db)


# ---------------------------------------------------------------------------
# Telegram operational helpers
# ---------------------------------------------------------------------------
@router.get("/telegram/status")
def telegram_status(admin: User = Depends(require_admin)) -> dict:
    result: dict = {
        "bot_configured": settings.bot_configured,
        "webhook_secret_configured": bool(settings.webhook_secret),
        "public_base_url": settings.public_base_url,
        "webapp_url": settings.webapp_url,
    }
    if settings.bot_configured:
        try:
            result["me"] = telegram_bot.get_me()
            result["webhook"] = telegram_bot.get_webhook_info()
        except telegram_bot.TelegramError as exc:
            result["error"] = str(exc)
    return result


@router.post("/telegram/setup-webhook", dependencies=[Depends(WRITE_LIMIT)])
def setup_webhook(
    request: Request,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    if not settings.bot_configured:
        raise HTTPException(400, "BOT_TOKEN не задан")
    if not settings.public_base_url.startswith("https://"):
        raise HTTPException(400, "PUBLIC_BASE_URL должен быть публичным HTTPS-адресом")
    url = f"{settings.public_base_url.rstrip('/')}/api/telegram/webhook"
    try:
        telegram_bot.set_webhook(url, settings.webhook_secret)
        info = telegram_bot.get_webhook_info()
    except telegram_bot.TelegramError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    audit.log_action(
        db, admin=admin, action="telegram.setup_webhook", after={"url": url}, request=request
    )
    db.commit()
    return {"ok": True, "url": url, "info": info}


@router.get("/admins", response_model=list[dict])
def list_admins(admin: User = Depends(require_superadmin), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AdminUser).options(joinedload(AdminUser.user))).unique().all()
    return [
        {
            "user_id": row.user_id,
            "role": row.role,
            "is_active": row.is_active,
            "username": row.user.username if row.user else "",
            "display_name": row.user.display_name if row.user else "",
        }
        for row in rows
    ]
