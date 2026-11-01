"""Telegram initData verification and access-control tests."""

from __future__ import annotations

import time

import pytest

from app.core.security import AuthError, build_init_data, validate_init_data
from app.core.config import settings
from tests.conftest import auth_headers


def test_valid_init_data_is_accepted():
    init_data = build_init_data(
        settings.bot_token, {"user": '{"id":42,"first_name":"A"}', "query_id": "q1"}
    )
    identity = validate_init_data(init_data)
    assert identity.telegram_id == 42
    assert identity.first_name == "A"


def test_tampered_init_data_is_rejected():
    init_data = build_init_data(settings.bot_token, {"user": '{"id":42}'}).replace("42", "43")
    with pytest.raises(AuthError):
        validate_init_data(init_data)


def test_expired_init_data_is_rejected():
    old = int(time.time()) - settings.init_data_max_age_seconds - 60
    init_data = build_init_data(settings.bot_token, {"user": '{"id":42}'}, auth_date=old)
    with pytest.raises(AuthError):
        validate_init_data(init_data)


def test_signature_from_other_bot_is_rejected():
    init_data = build_init_data("999:OTHER-TOKEN", {"user": '{"id":42}'})
    with pytest.raises(AuthError):
        validate_init_data(init_data)


def test_missing_authorization_returns_401(client):
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["auth_required"] is True


def test_invalid_authorization_returns_401(client):
    response = client.get("/api/me", headers={"Authorization": "tma garbage"})
    assert response.status_code == 401


def test_me_creates_user(client):
    response = client.get("/api/me", headers=auth_headers(700000123))
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["telegram_id"] == 700000123
    assert payload["is_admin"] is False


def test_admin_endpoints_require_admin_role(client, buyer, admin):
    assert client.get("/api/admin/overview", headers=buyer).status_code == 403
    assert client.get("/api/admin/overview", headers=admin).status_code == 200


def test_superadmin_can_change_commission_and_audit_is_recorded(client, admin, buyer):
    response = client.patch("/api/admin/settings", headers=admin, json={"commission_percent": 12})
    assert response.status_code == 200
    assert response.json()["commission_percent"] == 12

    config = client.get("/api/config").json()
    assert config["commission_percent"] == 12
    assert config["seller_share_percent"] == 88

    logs = client.get("/api/admin/audit-logs", headers=admin).json()
    assert any(row["action"] == "settings.update" for row in logs["items"])

    # Moderators cannot change economics.
    client.patch("/api/admin/users/1", headers=admin, json={"is_admin": True})
    response = client.patch("/api/admin/settings", headers=buyer, json={"commission_percent": 0})
    assert response.status_code == 403
