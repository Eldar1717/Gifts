"""Test configuration.

Environment variables are set *before* the application is imported so that the
settings singleton, engine and routers all pick up the test configuration.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TEST_DB = pathlib.Path(tempfile.gettempdir()) / "gift_market_tests.db"

os.environ.update(
    {
        "ENV": "development",
        "DATABASE_URL": f"sqlite:///{TEST_DB}",
        "BOT_TOKEN": "123456:TEST-TOKEN-FOR-SIGNATURE",
        "BOT_USERNAME": "gift_market_test_bot",
        "WEBHOOK_SECRET": "test-webhook-secret",
        "ADMIN_TELEGRAM_IDS": "500000000",
        "DEV_AUTH": "false",
        "COMMISSION_PERCENT": "10",
        "CORS_ORIGINS": "http://testserver",
    }
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import build_init_data  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Collection, CollectionItem, User  # noqa: E402
from app.services import notifications, telegram_bot  # noqa: E402


def auth_headers(telegram_id: int, *, username: str | None = None) -> dict[str, str]:
    """Create correctly signed Telegram initData for a virtual user."""
    init_data = build_init_data(
        settings.bot_token,
        {
            "user": (
                '{"id":%d,"first_name":"Test","last_name":"User","username":"%s"}'
                % (telegram_id, username or f"user_{telegram_id}")
            ),
            "query_id": "AAE-test",
        },
    )
    return {"Authorization": f"tma {init_data}"}


@pytest.fixture(autouse=True)
def _isolated_db():
    """Every test gets a brand new SQLite file (schema + data fully isolated)."""
    engine.dispose()
    TEST_DB.unlink(missing_ok=True)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    TEST_DB.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _silence_telegram(monkeypatch):
    """Never hit api.telegram.org from tests."""
    monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: True)
    monkeypatch.setattr(telegram_bot, "answer_pre_checkout_query", lambda *a, **k: True)
    monkeypatch.setattr(telegram_bot, "create_invoice_link", lambda **k: "https://t.me/$invoice-test")
    monkeypatch.setattr(telegram_bot, "refund_stars_payment", lambda *a, **k: True)
    monkeypatch.setattr(notifications, "deliver", lambda *a, **k: None)
    monkeypatch.setattr(notifications, "deliver_many", lambda *a, **k: None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_user(db, telegram_id: int, username: str | None = None) -> User:
    user = User(telegram_id=telegram_id, username=username or f"user_{telegram_id}", first_name="Test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_item(db, *, price: int = 100, edition: int = 10, name: str = "Test Gift") -> CollectionItem:
    collection = Collection(slug=f"c-{name.lower().replace(' ', '-')}", name=f"Collection {name}", status="active")
    db.add(collection)
    db.flush()
    item = CollectionItem(
        collection_id=collection.id,
        name=name,
        description="test",
        image_url="",
        rarity="rare",
        edition_size=edition,
        primary_price_stars=price,
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def buyer(client):
    return auth_headers(700000001, username="buyer")


@pytest.fixture
def seller(client):
    return auth_headers(700000002, username="seller")


@pytest.fixture
def admin(client):
    return auth_headers(500000000, username="admin")
