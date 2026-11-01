"""Telegram WebApp ``initData`` verification and authorization helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import HTTPException, status

from app.core.config import settings


class AuthError(HTTPException):
    def __init__(self, detail: str = "Telegram authorization failed") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@dataclass(frozen=True)
class TelegramIdentity:
    telegram_id: int
    username: str
    first_name: str
    last_name: str
    photo_url: str
    language_code: str
    is_premium: bool
    auth_date: int
    raw: dict


def _fail(detail: str) -> None:
    raise AuthError(detail)


def validate_init_data(init_data: str, *, now: float | None = None) -> TelegramIdentity:
    """Validate Telegram WebApp initData signature.

    Algorithm (official Telegram docs): the secret key is the HMAC-SHA256 of
    the bot token keyed by ``WebAppData``; the data-check-string is all fields
    sorted alphabetically and joined with ``\\n`` (``hash`` excluded).
    """
    if not settings.bot_token:
        # Without a bot token no signature can be validated. Fail closed.
        _fail("BOT_TOKEN is not configured on the server")

    if not init_data or len(init_data) > 8192:
        _fail("Missing or malformed initData")

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        _fail("Malformed initData")

    received_hash = pairs.pop("hash", "")
    if not received_hash or len(received_hash) != 64:
        _fail("Missing initData hash")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        _fail("Malformed auth_date")

    current = int(now if now is not None else time.time())
    max_age = settings.init_data_max_age_seconds
    if auth_date <= 0 or current - auth_date > max_age:
        _fail("Telegram session expired, reopen the Mini App")
    if auth_date > current + 300:
        _fail("auth_date is in the future")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        _fail("initData signature mismatch")

    try:
        payload = json.loads(pairs.get("user", "{}"))
        telegram_id = int(payload["id"])
        if telegram_id <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        _fail("initData user payload is invalid")

    return TelegramIdentity(
        telegram_id=telegram_id,
        username=str(payload.get("username") or ""),
        first_name=str(payload.get("first_name") or ""),
        last_name=str(payload.get("last_name") or ""),
        photo_url=str(payload.get("photo_url") or ""),
        language_code=str(payload.get("language_code") or ""),
        is_premium=bool(payload.get("is_premium", False)),
        auth_date=auth_date,
        raw=payload,
    )


def build_init_data(bot_token: str, fields: dict, *, auth_date: int | None = None) -> str:
    """Create signed initData. Used by the test-suite and local tooling only."""
    from urllib.parse import urlencode

    data = {key: str(value) for key, value in fields.items()}
    data["auth_date"] = str(auth_date or int(time.time()))
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)
