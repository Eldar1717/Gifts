"""End-to-end trading scenarios: listings, checkout, payments, ledger, refunds."""

from __future__ import annotations

import json
import uuid

from app.models import (
    GiftOwnership,
    MarketplaceListing,
    Order,
    Payment,
    SellerBalance,
    Transaction,
    User,
)
from app.services.ownership import grant_item
from tests.conftest import auth_headers, create_item, create_user

PAYMENT_CHARGE = "test-charge-{}".format(uuid.uuid4().hex)


def _grant(db, telegram_id: int, item, quantity: int = 1):
    user = db.query(User).filter_by(telegram_id=telegram_id).one()
    ownerships = []
    for _ in range(quantity):
        ownerships.append(grant_item(db, item=item, user=user, price=0, admin_id=1))
    db.commit()
    return ownerships


def _buyer_and_seller(db, item, price=None):
    seller = create_user(db, 710000001, "seller")
    buyer = create_user(db, 710000002, "buyer")
    ownership = grant_item(db, item=item, user=seller, price=0, admin_id=1)
    db.commit()
    listing = MarketplaceListing(
        ownership_id=ownership.id,
        seller_id=seller.id,
        price_stars=price or item.primary_price_stars,
        status="active",
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return seller, buyer, ownership, listing


def _listing_payload(listing_id: int) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "successful_payment": {
                "invoice_payload": "",
                "currency": "XTR",
                "total_amount": 0,
                "telegram_payment_charge_id": PAYMENT_CHARGE,
                "provider_payment_charge_id": "provider-1",
            },
        },
    }


def _webhook(client, payload: dict, update_id: int):
    body = json.loads(json.dumps(payload))
    body["update_id"] = update_id
    return client.post(
        "/api/telegram/webhook",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"},
    )


def test_primary_purchase_creates_ownership(client, db):
    item = create_item(db, price=500, edition=5, name="Primary One")
    headers = auth_headers(720000001)

    invoice = client.post("/api/checkout/invoice", headers=headers, json={"item_id": item.id})
    assert invoice.status_code == 200, invoice.text
    data = invoice.json()
    assert data["amount_stars"] == 500
    assert data["invoice_url"].startswith("https://")

    payment = db.query(Payment).filter_by(invoice_payload=data["order_number"]).first()
    assert payment is None  # payload differs from the human readable number
    order = db.get(Order, data["order_id"])
    payload = {
        "update_id": 10,
        "message": {
            "successful_payment": {
                "invoice_payload": order.payload,
                "currency": "XTR",
                "total_amount": 500,
                "telegram_payment_charge_id": "charge-primary-1",
                "provider_payment_charge_id": "provider-primary-1",
            }
        },
    }
    response = _webhook(client, payload, 10)
    assert response.status_code == 200

    db.expire_all()
    order = db.get(Order, data["order_id"])
    assert order.status == "fulfilled"
    assert order.ownership_id is not None
    ownership = db.get(GiftOwnership, order.ownership_id)
    buyer = db.query(User).filter_by(telegram_id=720000001).one()
    assert ownership.owner_id == buyer.id
    assert ownership.serial_number == 1

    item = db.get(type(item), item.id)
    assert item.minted_count == 1
    # Primary sales are platform revenue, no seller credit.
    assert order.seller_id is None
    commission = db.query(Transaction).filter_by(order_id=order.id).one()
    assert commission.bucket == "platform"
    assert commission.amount_stars == 500


def test_resale_flow_commission_and_seller_balance(client, db):
    item = create_item(db, price=800, edition=3, name="Resale One")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=500)
    buyer_headers = auth_headers(710000002)

    invoice = client.post(
        "/api/checkout/invoice", headers=buyer_headers, json={"listing_id": listing.id}
    )
    assert invoice.status_code == 200, invoice.text
    data = invoice.json()
    assert data["amount_stars"] == 500
    assert data["commission_stars"] == 50
    assert data["seller_amount_stars"] == 450

    order = db.get(Order, data["order_id"])
    payload = {
        "update_id": 20,
        "message": {
            "successful_payment": {
                "invoice_payload": order.payload,
                "currency": "XTR",
                "total_amount": 500,
                "telegram_payment_charge_id": "charge-resale-1",
                "provider_payment_charge_id": "provider-resale-1",
            }
        },
    }
    assert _webhook(client, payload, 20).status_code == 200

    db.expire_all()
    order = db.get(Order, order.id)
    listing = db.get(MarketplaceListing, listing.id)
    ownership = db.get(GiftOwnership, ownership.id)
    seller = db.query(User).filter_by(telegram_id=710000001).one()
    buyer = db.query(User).filter_by(telegram_id=710000002).one()

    assert order.status == "fulfilled"
    assert listing.status == "sold"
    assert ownership.owner_id == buyer.id
    assert seller.sales_count == 1
    assert buyer.purchases_count == 1

    balance = db.query(SellerBalance).filter_by(user_id=seller.id).one()
    assert balance.pending_stars == 450
    assert balance.lifetime_stars == 450

    ledger_rows = db.query(Transaction).filter_by(order_id=order.id).all()
    by_type = {row.type: row for row in ledger_rows}
    assert by_type["sale_credit"].amount_stars == 450
    assert by_type["commission"].amount_stars == 50
    assert by_type["commission"].bucket == "platform"


def test_commission_is_configurable_and_applied_to_new_sales(client, db, admin):
    assert client.patch(
        "/api/admin/settings", headers=admin, json={"commission_percent": 20}
    ).status_code == 200

    item = create_item(db, price=1000, edition=3, name="Resale Two")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=1000)
    invoice = client.post(
        "/api/checkout/invoice", headers=auth_headers(710000002), json={"listing_id": listing.id}
    )
    assert invoice.status_code == 200, invoice.text
    data = invoice.json()
    assert data["commission_stars"] == 200
    assert data["seller_amount_stars"] == 800

    order = db.get(Order, data["order_id"])
    payload = {
        "update_id": 30,
        "message": {
            "successful_payment": {
                "invoice_payload": order.payload,
                "currency": "XTR",
                "total_amount": 1000,
                "telegram_payment_charge_id": "charge-config-1",
                "provider_payment_charge_id": "provider-config-1",
            }
        },
    }
    assert _webhook(client, payload, 30).status_code == 200
    db.expire_all()
    balance = db.query(SellerBalance).filter_by(user_id=seller.id).one()
    assert balance.pending_stars == 800


def test_second_buyer_cannot_reserve_same_listing(client, db):
    item = create_item(db, price=300, edition=3, name="Resale Three")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=300)
    other = create_user(db, 710000003, "other")

    first = client.post(
        "/api/checkout/invoice", headers=auth_headers(buyer.telegram_id), json={"listing_id": listing.id}
    )
    assert first.status_code == 200

    second = client.post(
        "/api/checkout/invoice", headers=auth_headers(other.telegram_id), json={"listing_id": listing.id}
    )
    assert second.status_code == 409
    assert "недоступ" in second.json()["detail"].lower() or "продаж" in second.json()["detail"].lower()

    db.expire_all()
    assert db.get(MarketplaceListing, listing.id).status == "reserved"


def test_seller_cannot_buy_own_listing(client, db):
    item = create_item(db, price=100, edition=3, name="Resale Four")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=100)
    response = client.post(
        "/api/checkout/invoice",
        headers=auth_headers(seller.telegram_id),
        json={"listing_id": listing.id},
    )
    assert response.status_code == 409


def test_price_is_taken_from_database_not_client(client, db):
    item = create_item(db, price=100, edition=3, name="Resale Five")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=100)
    response = client.post(
        "/api/checkout/invoice",
        headers=auth_headers(buyer.telegram_id),
        json={"listing_id": listing.id, "price_stars": 1, "amount_stars": 1, "commission_stars": 0},
    )
    assert response.status_code == 200
    assert response.json()["amount_stars"] == 100


def test_webhook_is_idempotent(client, db):
    item = create_item(db, price=500, edition=3, name="Resale Six")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=500)
    invoice = client.post(
        "/api/checkout/invoice", headers=auth_headers(buyer.telegram_id), json={"listing_id": listing.id}
    ).json()
    order = db.get(Order, invoice["order_id"])
    payload = {
        "update_id": 40,
        "message": {
            "successful_payment": {
                "invoice_payload": order.payload,
                "currency": "XTR",
                "total_amount": 500,
                "telegram_payment_charge_id": "charge-idem-1",
                "provider_payment_charge_id": "provider-idem-1",
            }
        },
    }
    assert _webhook(client, payload, 40).status_code == 200
    # Same update replayed, then the same charge with a different update id.
    assert _webhook(client, payload, 40).status_code == 200
    assert _webhook(client, payload, 41).status_code == 200

    db.expire_all()
    balance = db.query(SellerBalance).filter_by(user_id=seller.id).one()
    assert balance.pending_stars == 450
    credits = [
        row
        for row in db.query(Transaction).filter_by(order_id=order.id).all()
        if row.type == "sale_credit"
    ]
    assert len(credits) == 1
    assert db.get(MarketplaceListing, listing.id).status == "sold"


def test_webhook_rejects_amount_mismatch(client, db):
    item = create_item(db, price=500, edition=3, name="Resale Seven")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=500)
    invoice = client.post(
        "/api/checkout/invoice", headers=auth_headers(buyer.telegram_id), json={"listing_id": listing.id}
    ).json()
    order = db.get(Order, invoice["order_id"])
    payload = {
        "update_id": 50,
        "message": {
            "successful_payment": {
                "invoice_payload": order.payload,
                "currency": "XTR",
                "total_amount": 1,
                "telegram_payment_charge_id": "charge-bad-1",
            }
        },
    }
    assert _webhook(client, payload, 50).status_code == 200
    db.expire_all()
    order = db.get(Order, order.id)
    assert order.status == "pending_payment"
    assert db.get(MarketplaceListing, listing.id).status == "reserved"


def test_webhook_requires_secret(client, db):
    response = client.post("/api/telegram/webhook", json={"update_id": 60})
    assert response.status_code == 403


def test_pre_checkout_query_validation(client, db):
    item = create_item(db, price=250, edition=3, name="Resale Eight")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=250)
    invoice = client.post(
        "/api/checkout/invoice", headers=auth_headers(buyer.telegram_id), json={"listing_id": listing.id}
    ).json()
    order = db.get(Order, invoice["order_id"])

    ok_payload = {
        "update_id": 70,
        "pre_checkout_query": {
            "id": "pcq-1",
            "invoice_payload": order.payload,
            "currency": "XTR",
            "total_amount": 250,
        },
    }
    assert _webhook(client, ok_payload, 70).status_code == 200

    bad_payload = {
        "update_id": 71,
        "pre_checkout_query": {
            "id": "pcq-2",
            "invoice_payload": order.payload,
            "currency": "XTR",
            "total_amount": 5,
        },
    }
    assert _webhook(client, bad_payload, 71).status_code == 200
    db.expire_all()
    assert db.get(Order, order.id).status == "pending_payment"


def test_listing_lifecycle(client, db):
    item = create_item(db, price=400, edition=3, name="Lifecycle Gift")
    user = create_user(db, 730000001, "lifecycle")
    ownership = grant_item(db, item=item, user=user, price=0, admin_id=1)
    db.commit()
    headers = auth_headers(user.telegram_id)

    created = client.post("/api/listings", headers=headers, json={"ownership_id": ownership.id, "price_stars": 600})
    assert created.status_code == 201, created.text
    listing_id = created.json()["listing"]["id"]
    assert created.json()["seller_receives_stars"] == 540

    duplicate = client.post("/api/listings", headers=headers, json={"ownership_id": ownership.id, "price_stars": 700})
    assert duplicate.status_code == 409

    below_minimum = client.post("/api/listings", headers=headers, json={"ownership_id": ownership.id, "price_stars": 1})
    assert below_minimum.status_code in {409, 400}

    repriced = client.patch(f"/api/listings/{listing_id}", headers=headers, json={"price_stars": 750})
    assert repriced.status_code == 200
    assert repriced.json()["price_stars"] == 750

    cancelled = client.delete(f"/api/listings/{listing_id}", headers=headers)
    assert cancelled.status_code == 200

    relisted = client.post("/api/listings", headers=headers, json={"ownership_id": ownership.id, "price_stars": 900})
    assert relisted.status_code == 201

    other = auth_headers(730000002)
    forbidden = client.delete(f"/api/listings/{listing_id}", headers=other)
    assert forbidden.status_code in {403, 404, 409}


def test_cannot_list_someone_elses_gift(client, db):
    item = create_item(db, price=100, edition=3, name="Others Gift")
    owner = create_user(db, 740000001)
    stranger = create_user(db, 740000002)
    ownership = grant_item(db, item=item, user=owner, price=0, admin_id=1)
    db.commit()
    response = client.post(
        "/api/listings",
        headers=auth_headers(stranger.telegram_id),
        json={"ownership_id": ownership.id, "price_stars": 200},
    )
    assert response.status_code == 409


def test_blocked_user_cannot_checkout(client, db):
    item = create_item(db, price=100, edition=5, name="Blocked Gift")
    user = create_user(db, 750000001, "blocked")
    user.is_blocked = True
    db.commit()
    response = client.post(
        "/api/checkout/invoice", headers=auth_headers(user.telegram_id), json={"item_id": item.id}
    )
    assert response.status_code == 403


def test_favorites_and_notifications(client, db):
    item = create_item(db, price=100, edition=5, name="Fav Gift")
    headers = auth_headers(760000001)
    assert client.post(f"/api/favorites/{item.id}", headers=headers).json()["favorite"] is True
    favorites = client.get("/api/favorites", headers=headers).json()
    assert len(favorites) == 1
    assert client.post(f"/api/favorites/{item.id}", headers=headers).json()["favorite"] is False
    assert client.get("/api/favorites", headers=headers).json() == []

    notifications = client.get("/api/notifications", headers=headers).json()
    assert notifications["total"] >= 0


def test_offer_flow_creates_listing(client, db):
    item = create_item(db, price=500, edition=5, name="Offer Gift")
    owner = create_user(db, 770000001)
    buyer = create_user(db, 770000002)
    ownership = grant_item(db, item=item, user=owner, price=0, admin_id=1)
    db.commit()

    offer = client.post(
        "/api/offers",
        headers=auth_headers(buyer.telegram_id),
        json={"ownership_id": ownership.id, "price_stars": 650, "message": "Беру сегодня"},
    )
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()["id"]

    incoming = client.get("/api/me/offers", headers=auth_headers(owner.telegram_id)).json()
    assert len(incoming) == 1 and incoming[0]["price_stars"] == 650

    accepted = client.post(f"/api/offers/{offer_id}/accept", headers=auth_headers(owner.telegram_id))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["price_stars"] == 650

    listing = db.get(MarketplaceListing, accepted.json()["listing_id"])
    assert listing.status == "active"
    assert listing.price_stars == 650


def test_payout_request_moves_funds_to_withdrawal(client, db):
    item = create_item(db, price=1000, edition=3, name="Payout Gift")
    seller, buyer, ownership, listing = _buyer_and_seller(db, item, price=1000)
    invoice = client.post(
        "/api/checkout/invoice", headers=auth_headers(buyer.telegram_id), json={"listing_id": listing.id}
    ).json()
    order = db.get(Order, invoice["order_id"])
    payload = {
        "update_id": 80,
        "message": {
            "successful_payment": {
                "invoice_payload": order.payload,
                "currency": "XTR",
                "total_amount": 1000,
                "telegram_payment_charge_id": "charge-payout-1",
            }
        },
    }
    assert _webhook(client, payload, 80).status_code == 200

    seller_headers = auth_headers(seller.telegram_id)
    # Funds are still in the hold period: payout must be rejected.
    too_early = client.post(
        "/api/me/payouts", headers=seller_headers, json={"amount_stars": 900, "method": "stars_manual"}
    )
    assert too_early.status_code == 400

    # Simulate the hold window passing.
    from app.db.base import utcnow
    from app.services import ledger
    session = db
    order = session.get(Order, order.id)
    order.hold_until = utcnow()
    session.commit()
    assert ledger.settle_due_holds(session) == 1
    session.commit()

    payout = client.post(
        "/api/me/payouts",
        headers=seller_headers,
        json={"amount_stars": 500, "method": "stars_manual", "destination": "@seller"},
    )
    assert payout.status_code == 200, payout.text
    assert payout.json()["status"] == "requested"

    balance = client.get("/api/me/balance", headers=seller_headers).json()
    assert balance["available_stars"] == 400

    admin_headers = auth_headers(500000000)
    approved = client.post(
        f"/api/admin/payouts/{payout.json()['id']}",
        headers=admin_headers,
        json={"status": "approved", "admin_note": "ok", "external_reference": ""},
    )
    assert approved.status_code == 200
    paid = client.post(
        f"/api/admin/payouts/{payout.json()['id']}",
        headers=admin_headers,
        json={"status": "paid", "admin_note": "sent", "external_reference": "tx-1"},
    )
    assert paid.status_code == 200
    balance = client.get("/api/me/balance", headers=seller_headers).json()
    assert balance["withdrawn_stars"] == 500


def test_home_and_market_expose_active_catalogue(client, db):
    item = create_item(db, price=100, edition=5, name="Catalog Gift")
    user = create_user(db, 780000001)
    ownership = grant_item(db, item=item, user=user, price=0, admin_id=1)
    db.commit()
    db.add(
        MarketplaceListing(
            ownership_id=ownership.id, seller_id=user.id, price_stars=150, status="active"
        )
    )
    db.commit()

    market = client.get("/api/market").json()
    assert market["total"] >= 2  # primary mint + resale listing
    kinds = {card["kind"] for card in market["items"]}
    assert kinds == {"primary", "resale"}

    home = client.get("/api/home").json()
    assert len(home["featured"]) >= 1
    assert home["stats"]["active_listings"] >= 1

    detail = client.get(f"/api/items/{item.id}").json()
    assert detail["item"]["name"] == "Catalog Gift"
    assert detail["kind"] == "resale"
