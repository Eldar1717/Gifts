"""Seed GIFT MARKET with a demonstrable catalogue and trading history.

Usage (from ``backend/``, with the virtualenv activated)::

    python seed.py            # seed an empty database
    python seed.py --reset    # drop and recreate every table (development only)

The script refuses to run in production. All monetary values are written
through the same services used by the API, so balances, ledger entries and
ownership history stay consistent.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.enums import (
    AdminRole,
    ListingStatus,
    NotificationType,
    OrderStatus,
    OrderType,
    OwnershipEvent,
    PaymentStatus,
    PriceEvent,
    PriceHistoryScope,
    Rarity,
)
from app.db.base import Base, utcnow
from app.db.session import SessionLocal, engine
from app.models import (
    AdminUser,
    Category,
    Collection,
    CollectionItem,
    Favorite,
    GiftOwnership,
    MarketplaceListing,
    Offer,
    Order,
    OwnershipHistory,
    Payment,
    PlatformSettings,
    PriceHistory,
    Review,
    SellerBalance,
    Transaction,
    User,
)
from app.services import ledger, notifications
from app.services.marketplace import create_listing
from app.services.ownership import grant_item, transfer_resale
from app.services.pricing import split_amount

rng = random.Random(42)
NOW = utcnow()

CATEGORIES = [
    ("relics", "Древние реликвии", "Артефакты с историей и характером", "🏺", 1),
    ("cosmos", "Космос", "Лёд, звёзды и далёкие орбиты", "🌌", 2),
    ("nature", "Природа", "Рост, жизнь и зелёный свет", "🌿", 3),
    ("artifacts", "Артефакты", "Оружие, короны и трофеи", "⚔️", 4),
    ("abstract", "Абстракция", "Форма, цвет и чистый свет", "🎨", 5),
]

COLLECTIONS = [
    {
        "slug": "dragon-relics",
        "name": "Драконьи Реликвии",
        "description": "Осколки древней драконьей эпохи: золото, обсидиан и огонь, застывший внутри камня.",
        "cover": "/gifts/aurum-drake.jpg",
        "accent": "#f5b544",
        "category": "relics",
        "rarity": Rarity.LEGENDARY,
        "featured": True,
        "days_ago": 40,
        "items": [
            {
                "name": "Aurum Drake",
                "description": "Золотое драконье яйцо из обсидиановой чешуи. Легендарный предмет с ограниченным тиражом 25 экземпляров.",
                "image": "/gifts/aurum-drake.jpg",
                "glow": "#f5b544",
                "rarity": Rarity.LEGENDARY,
                "price": 2500,
                "edition": 25,
                "featured": True,
            },
            {
                "name": "Obsidian Crown",
                "description": "Корона из чёрного обсидиана с прожилками лавы. Символ власти коллекционера.",
                "image": "/gifts/obsidian-crown.jpg",
                "glow": "#f97316",
                "rarity": Rarity.EPIC,
                "price": 900,
                "edition": 60,
                "featured": True,
            },
        ],
    },
    {
        "slug": "crystal-hearts",
        "name": "Кристальные Сердца",
        "description": "Кристаллы, которые бьются чаще, если рядом настоящий коллекционер.",
        "cover": "/gifts/crystal-heart.jpg",
        "accent": "#a855f7",
        "category": "abstract",
        "rarity": Rarity.EPIC,
        "featured": True,
        "days_ago": 30,
        "items": [
            {
                "name": "Violet Heart",
                "description": "Гранёное сердце из аметиста в серебряной филиграни. Светится изнутри холодным малиновым светом.",
                "image": "/gifts/crystal-heart.jpg",
                "glow": "#a855f7",
                "rarity": Rarity.EPIC,
                "price": 780,
                "edition": 80,
                "featured": True,
            },
            {
                "name": "Amethyst Pulse",
                "description": "Пульс аметиста — редкий оттиск энергии кристалла, пойманный в момент свечения.",
                "image": "/gifts/crystal-heart.jpg",
                "glow": "#c084fc",
                "rarity": Rarity.RARE,
                "price": 420,
                "edition": 150,
                "featured": False,
            },
        ],
    },
    {
        "slug": "glacier-edge",
        "name": "Ледяная Грань",
        "description": "Коллекция для тех, кто ценит холодную геометрию и северное сияние.",
        "cover": "/gifts/ice-star.jpg",
        "accent": "#38bdf8",
        "category": "cosmos",
        "rarity": Rarity.RARE,
        "featured": True,
        "days_ago": 22,
        "items": [
            {
                "name": "Glacier Star",
                "description": "Звезда из древнего льда. Каждая грань отражает свет по-своему.",
                "image": "/gifts/ice-star.jpg",
                "glow": "#38bdf8",
                "rarity": Rarity.RARE,
                "price": 350,
                "edition": 120,
                "featured": True,
            },
            {
                "name": "Frost Comet",
                "description": "Осколок кометы, остывший на орбите. Необычная находка для спокойной коллекции.",
                "image": "/gifts/ice-star.jpg",
                "glow": "#60a5fa",
                "rarity": Rarity.UNCOMMON,
                "price": 180,
                "edition": 200,
                "featured": False,
            },
        ],
    },
    {
        "slug": "emerald-garden",
        "name": "Изумрудный Сад",
        "description": "Живые формы, выращенные из стекла и света. Тираж шире, но красивых номеров на всех не хватает.",
        "cover": "/gifts/emerald-clover.jpg",
        "accent": "#34d399",
        "category": "nature",
        "rarity": Rarity.UNCOMMON,
        "featured": False,
        "days_ago": 16,
        "items": [
            {
                "name": "Emerald Clover",
                "description": "Четырёхлистный клевер из изумрудного стекла с золотым стеблем.",
                "image": "/gifts/emerald-clover.jpg",
                "glow": "#34d399",
                "rarity": Rarity.UNCOMMON,
                "price": 120,
                "edition": 300,
                "featured": True,
            },
            {
                "name": "Verdant Sigil",
                "description": "Печать весны — компактный символ роста для начинающих коллекционеров.",
                "image": "/gifts/emerald-clover.jpg",
                "glow": "#10b981",
                "rarity": Rarity.COMMON,
                "price": 60,
                "edition": 500,
                "featured": False,
            },
        ],
    },
    {
        "slug": "rose-quartz",
        "name": "Розовый Кварц",
        "description": "Самая тёплая коллекция маркета: мягкий свет, розовый кварц и подарочные ленты.",
        "cover": "/gifts/rose-quartz.jpg",
        "accent": "#fb7185",
        "category": "abstract",
        "rarity": Rarity.COMMON,
        "featured": False,
        "days_ago": 10,
        "items": [
            {
                "name": "Rose Quartz Bow",
                "description": "Лента, выточенная из розового кварца. Классический подарок с идеальным свечением.",
                "image": "/gifts/rose-quartz.jpg",
                "glow": "#fb7185",
                "rarity": Rarity.COMMON,
                "price": 45,
                "edition": 750,
                "featured": False,
            },
            {
                "name": "Blush Ribbon",
                "description": "Лёгкий штрих к любой коллекции — нежный розовый бант с атласным блеском.",
                "image": "/gifts/rose-quartz.jpg",
                "glow": "#fda4af",
                "rarity": Rarity.COMMON,
                "price": 30,
                "edition": 1000,
                "featured": False,
            },
        ],
    },
    {
        "slug": "night-ash",
        "name": "Ночной Пепел",
        "description": "Тёмная коллекция о том, что остаётся после огня. Ограниченные серии, высокий спрос.",
        "cover": "/gifts/obsidian-crown.jpg",
        "accent": "#f97316",
        "category": "relics",
        "rarity": Rarity.EPIC,
        "featured": True,
        "days_ago": 6,
        "items": [
            {
                "name": "Ember Crown",
                "description": "Корона из пепла и углей. Второй шанс для легендарной формы.",
                "image": "/gifts/obsidian-crown.jpg",
                "glow": "#f97316",
                "rarity": Rarity.EPIC,
                "price": 650,
                "edition": 90,
                "featured": True,
            },
            {
                "name": "Cinder Egg",
                "description": "Яйцо из застывшего пепла — редкий предмет ночной коллекции.",
                "image": "/gifts/aurum-drake.jpg",
                "glow": "#fb923c",
                "rarity": Rarity.RARE,
                "price": 480,
                "edition": 140,
                "featured": False,
            },
        ],
    },
]

COLLECTORS = [
    (900000001, "demo_collector", "Демид", "Орлов"),
    (900000002, "lunar_maria", "Мария", "Лунар"),
    (900000003, "kai_flux", "Кай", "Флюкс"),
    (900000004, "nora_vault", "Нора", "Волкова"),
    (900000005, "atlas_shop", "Атлас", "Громов"),
    (900000006, "mira_gems", "Мира", "Стелла"),
]


def _fail(message: str) -> None:
    print(f"✖ {message}")
    sys.exit(1)


def seed(reset: bool = False) -> None:
    if settings.is_production:
        _fail("Seeding is disabled in production (ENV=production).")

    if reset:
        print("• Dropping all tables…")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.scalar(select(Collection.id).limit(1)):
            print("• Database already contains data — nothing to seed.")
            print("  Use `python seed.py --reset` for a clean demo dataset (development only).")
            return

        platform = db.get(PlatformSettings, 1)
        if platform is None:
            db.add(
                PlatformSettings(
                    id=1,
                    commission_percent=settings.commission_percent,
                    min_listing_price=settings.min_listing_price,
                    max_listing_price=settings.max_listing_price,
                    hold_hours=settings.balance_hold_hours,
                    min_payout_stars=100,
                    payout_note=(
                        "Внутренний баланс — не банковский кошелёк. Выплаты выполняются вручную "
                        "после проверки и согласования; заявка не гарантирует автоматический вывод Stars."
                    ),
                    terms_url="",
                )
            )
            db.commit()
            platform = db.get(PlatformSettings, 1)

        # --- users ---------------------------------------------------------
        admin_tg = min(settings.admin_ids) if settings.admin_ids else 900000000
        admin = User(
            telegram_id=admin_tg,
            username="giftmarket_admin",
            first_name="Gift Market",
            last_name="Admin",
            is_admin=True,
            photo_url="",
        )
        db.add(admin)
        db.flush()
        db.add(AdminUser(user_id=admin.id, role=AdminRole.SUPERADMIN.value, is_active=True))

        users: list[User] = []
        for telegram_id, username, first, last in COLLECTORS:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first,
                last_name=last,
                photo_url="",
                rating_count=0,
                rating_sum=0,
                created_at=NOW - timedelta(days=rng.randint(20, 90)),
            )
            db.add(user)
            users.append(user)
        db.flush()

        # --- catalogue -----------------------------------------------------
        categories: dict[str, Category] = {}
        for slug, name, description, emoji, order in CATEGORIES:
            category = Category(
                slug=slug, name=name, description=description, emoji=emoji, sort_order=order
            )
            db.add(category)
            categories[slug] = category
        db.flush()

        items: list[CollectionItem] = []
        for position, data in enumerate(COLLECTIONS):
            collection = Collection(
                slug=data["slug"],
                name=data["name"],
                description=data["description"],
                cover_url=data["cover"],
                accent=data["accent"],
                category_id=categories[data["category"]].id,
                rarity=data["rarity"].value,
                status="active",
                is_featured=data["featured"],
                released_at=NOW - timedelta(days=data["days_ago"]),
                created_at=NOW - timedelta(days=data["days_ago"]),
            )
            db.add(collection)
            db.flush()
            for item_data in data["items"]:
                item = CollectionItem(
                    collection_id=collection.id,
                    name=item_data["name"],
                    description=item_data["description"],
                    image_url=item_data["image"],
                    back_image_url=item_data["image"],
                    glow=item_data["glow"],
                    rarity=item_data["rarity"].value,
                    edition_size=item_data["edition"],
                    primary_price_stars=item_data["price"],
                    status="active",
                    is_featured=item_data["featured"],
                    is_limited=True,
                    is_serialized=True,
                    source="internal",
                    is_tradeable=True,
                    created_at=NOW - timedelta(days=data["days_ago"]),
                )
                db.add(item)
                items.append(item)
        db.commit()
        print(f"• Collections: {len(COLLECTIONS)}, gifts: {len(items)}, users: {len(users) + 1}")

        # --- initial mint (platform grants) --------------------------------
        ownerships: list[GiftOwnership] = []
        for item in items:
            copies = rng.randint(4, 6)
            for _ in range(copies):
                owner = rng.choice(users)
                ownership = grant_item(db, item=item, user=owner, price=0, admin_id=admin.id)
                acquired = NOW - timedelta(days=rng.randint(2, 28), hours=rng.randint(0, 20))
                ownership.acquired_at = acquired
                ownership.created_at = acquired
                ownerships.append(ownership)
        db.commit()
        print(f"• Minted {len(ownerships)} collectibles")

        # --- trading history ----------------------------------------------
        sold = 0
        history_rows = 0
        for ownership in rng.sample(ownerships, k=10):
            seller = db.get(User, ownership.owner_id)
            buyer = rng.choice([u for u in users if u.id != seller.id])
            price = max(10, int(ownership.item.primary_price_stars * rng.uniform(1.05, 1.9)) // 10 * 10)
            split = split_amount(price, platform.commission_percent)
            sold_at = NOW - timedelta(days=rng.randint(1, 12), hours=rng.randint(1, 20))
            order = Order(
                order_number=f"GM-{sold_at:%y%m%d}-{rng.randrange(16**6):06X}",
                payload=f"seed-{ownership.id}-{sold_at.timestamp():.0f}",
                buyer_id=buyer.id,
                seller_id=seller.id,
                item_id=ownership.item_id,
                ownership_id=ownership.id,
                order_type=OrderType.RESALE.value,
                status=OrderStatus.FULFILLED.value,
                amount_stars=price,
                commission_percent=split.commission_percent,
                commission_stars=split.commission_stars,
                seller_amount_stars=split.seller_stars,
                created_at=sold_at - timedelta(minutes=6),
                paid_at=sold_at - timedelta(minutes=5),
                fulfilled_at=sold_at,
                hold_until=None,
            )
            db.add(order)
            db.flush()
            db.add(
                Payment(
                    order_id=order.id,
                    invoice_payload=order.payload,
                    telegram_payment_charge_id=f"seed-charge-{order.id:06d}",
                    provider_payment_charge_id=f"seed-provider-{order.id:06d}",
                    amount_stars=price,
                    status=PaymentStatus.SUCCEEDED.value,
                    paid_at=order.paid_at,
                    created_at=order.created_at,
                    is_test=True,
                )
            )
            transfer_resale(db, ownership=ownership, order=order)
            history_row = db.scalar(
                select(OwnershipHistory)
                .where(
                    OwnershipHistory.ownership_id == ownership.id,
                    OwnershipHistory.order_id == order.id,
                )
                .order_by(OwnershipHistory.id.desc())
            )
            if history_row:
                history_row.created_at = sold_at
                history_row.event = OwnershipEvent.RESALE.value
                history_rows += 1
            ownership.acquired_at = sold_at
            ownership.created_at = sold_at
            order.ownership_id = ownership.id
            ledger.credit_sale(db, order)
            ledger.release_pending(db, order)
            for transaction in db.scalars(
                select(Transaction).where(Transaction.order_id == order.id)
            ).all():
                transaction.created_at = sold_at
            db.add(
                PriceHistory(
                    item_id=order.item_id,
                    ownership_id=ownership.id,
                    scope=PriceHistoryScope.OWNERSHIP.value,
                    event=PriceEvent.SOLD.value,
                    price_stars=price,
                    created_at=sold_at,
                )
            )
            sold += 1
        db.commit()
        print(f"• Seeded {sold} completed sales with ownership history")

        # --- reviews -------------------------------------------------------
        fulfilled = db.scalars(
            select(Order).where(Order.status == OrderStatus.FULFILLED.value).limit(4)
        ).all()
        for order in fulfilled[:3]:
            rating = rng.choice([5, 5, 4])
            db.add(
                Review(
                    order_id=order.id,
                    author_id=order.buyer_id,
                    seller_id=order.seller_id,
                    rating=rating,
                    comment=rng.choice(
                        [
                            "Быстрая сделка, подарок пришёл мгновенно. Рекомендую!",
                            "Всё как на фото, приятная упаковка карточки.",
                            "Спокойный продавец, номер экземпляра отличный.",
                            "Оплатил Stars — предмет сразу в коллекции.",
                        ]
                    ),
                    created_at=order.fulfilled_at + timedelta(hours=2),
                )
            )
            seller = db.get(User, order.seller_id)
            seller.rating_count += 1
            seller.rating_sum += rating
        db.commit()

        # --- active listings ----------------------------------------------
        listed = 0
        candidates = [
            ownership
            for ownership in db.scalars(select(GiftOwnership)).all()
            if ownership.status == "owned"
        ]
        rng.shuffle(candidates)
        for ownership in candidates:
            if listed >= 7:
                break
            existing = db.scalar(
                select(MarketplaceListing).where(
                    MarketplaceListing.ownership_id == ownership.id,
                    MarketplaceListing.status.in_(
                        [ListingStatus.ACTIVE.value, ListingStatus.RESERVED.value]
                    ),
                )
            )
            if existing:
                continue
            price = max(10, int(ownership.item.primary_price_stars * rng.uniform(1.1, 2.3)) // 10 * 10)
            try:
                listing = create_listing(
                    db, user=db.get(User, ownership.owner_id), ownership_id=ownership.id, price_stars=price
                )
            except Exception:
                db.rollback()
                continue
            listed_at = NOW - timedelta(hours=rng.randint(1, 96))
            listing.listed_at = listed_at
            listing.created_at = listed_at
            listing.views = rng.randint(3, 180)
            db.add(
                PriceHistory(
                    item_id=ownership.item_id,
                    ownership_id=ownership.id,
                    listing_id=listing.id,
                    scope=PriceHistoryScope.GIFT.value,
                    event=PriceEvent.LISTED.value,
                    price_stars=price,
                    created_at=listed_at,
                )
            )
            listed += 1
        db.commit()
        print(f"• Created {listed} active marketplace listings")

        # --- offers --------------------------------------------------------
        demo = next(user for user in users if user.telegram_id == settings.demo_telegram_id)
        other_owned = db.scalars(
            select(GiftOwnership)
            .where(GiftOwnership.owner_id != demo.id)
            .limit(10)
        ).all()
        offer_created = 0
        for ownership in other_owned:
            if offer_created >= 2:
                break
            price = max(10, ownership.item.primary_price_stars // 2 // 10 * 10)
            db.add(
                Offer(
                    ownership_id=ownership.id,
                    buyer_id=demo.id,
                    seller_id=ownership.owner_id,
                    price_stars=price,
                    message="Готов забрать сегодня, если устроит цена.",
                    status="pending",
                    created_at=NOW - timedelta(hours=rng.randint(2, 40)),
                )
            )
            offer_created += 1
        demo_owned = db.scalars(
            select(GiftOwnership).where(GiftOwnership.owner_id == demo.id).limit(5)
        ).all()
        incoming_item = next(
            (ownership for ownership in demo_owned if ownership.item.primary_price_stars > 100),
            demo_owned[0] if demo_owned else None,
        )
        if incoming_item:
            buyer = next(user for user in users if user.id != demo.id)
            db.add(
                Offer(
                    ownership_id=incoming_item.id,
                    buyer_id=buyer.id,
                    seller_id=demo.id,
                    price_stars=max(10, incoming_item.item.primary_price_stars // 10 * 12),
                    message="Интересен именно этот номер. Предлагаю свою цену.",
                    status="pending",
                    created_at=NOW - timedelta(hours=6),
                )
            )
        db.commit()

        # --- favourites & notifications -----------------------------------
        for item in rng.sample(items, k=4):
            db.add(Favorite(user_id=demo.id, item_id=item.id, created_at=NOW - timedelta(days=2)))
        notifications.create_notification(
            db,
            demo,
            type=NotificationType.SYSTEM,
            title="Добро пожаловать в GIFT MARKET",
            body=(
                "Это демонстрационный каталог. Покупайте подарки за Telegram Stars, "
                "собирайте коллекцию и перепродавайте предметы другим коллекционерам."
            ),
            telegram=False,
        )
        db.commit()

        demo_balance = db.scalar(select(SellerBalance).where(SellerBalance.user_id == demo.id))
        demo_items = db.scalar(
            select(GiftOwnership.id).where(GiftOwnership.owner_id == demo.id).limit(1)
        )
        print("")
        print("✔ Demo data ready")
        print(f"  admin Telegram ID : {admin_tg}")
        print(f"  demo user          : {demo.telegram_id} (@{demo.username})")
        print(f"  demo gifts         : {'yes' if demo_items else 'no'}")
        if demo_balance:
            print(
                f"  demo balance       : pending {demo_balance.pending_stars} / "
                f"available {demo_balance.available_stars} Stars"
            )
        print("  images             : /gifts/*.jpg (served by the frontend)")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed GIFT MARKET demo data")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()
    seed(reset=args.reset)
