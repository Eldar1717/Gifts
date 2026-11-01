"""Thin Telegram Bot API client used by the backend.

No third-party bot framework is required: the API calls used by the
marketplace are few and explicit. All calls fail closed with a typed error.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    def __init__(self, method: str, description: str, status_code: int | None = None) -> None:
        self.method = method
        self.description = description
        self.status_code = status_code
        super().__init__(f"Telegram {method} failed: {description}")


def is_configured() -> bool:
    return bool(settings.bot_token)


def _call(method: str, payload: dict[str, Any] | None = None, *, timeout: float = 15.0) -> Any:
    if not settings.bot_token:
        raise TelegramError(method, "BOT_TOKEN is not configured")
    url = f"{API_BASE}/bot{settings.bot_token}/{method}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload or {})
    except httpx.HTTPError as exc:  # network level failure
        logger.error("telegram.network_error", extra={"event": method})
        raise TelegramError(method, f"network error: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        raise TelegramError(method, "invalid JSON response", response.status_code) from None
    if not data.get("ok"):
        description = str(data.get("description", "unknown error"))
        logger.warning(
            "telegram.api_error", extra={"event": method, "status_code": response.status_code}
        )
        raise TelegramError(method, description, response.status_code)
    return data.get("result")


def create_invoice_link(
    *,
    title: str,
    description: str,
    payload: str,
    amount_stars: int,
    photo_url: str = "",
) -> str:
    """Create a Telegram Stars invoice link (currency XTR, empty provider token)."""
    body: dict[str, Any] = {
        "title": title[:32],
        "description": description[:255],
        "payload": payload,
        "currency": "XTR",
        "prices": [{"label": title[:32], "amount": amount_stars}],
    }
    if photo_url.startswith("https://"):
        body["photo_url"] = photo_url
    result = _call("createInvoiceLink", body)
    if not isinstance(result, str) or not result.startswith("https://"):
        raise TelegramError("createInvoiceLink", "unexpected invoice link")
    return result


def answer_pre_checkout_query(query_id: str, ok: bool, error_message: str = "") -> bool:
    body: dict[str, Any] = {"pre_checkout_query_id": query_id, "ok": ok}
    if not ok:
        body["error_message"] = (error_message or "Заказ недоступен")[:200]
    return bool(_call("answerPreCheckoutQuery", body))


def refund_stars_payment(telegram_user_id: int, charge_id: str) -> bool:
    """Refund a Stars payment. Telegram only allows refunds for XTR payments."""
    return bool(
        _call(
            "refundStarPayment",
            {"user_id": telegram_user_id, "telegram_payment_charge_id": charge_id},
        )
    )


def send_message(chat_id: int, text: str, *, markup: dict | None = None) -> bool:
    body: dict[str, Any] = {"chat_id": chat_id, "text": text[:4096]}
    if markup:
        body["reply_markup"] = markup
    return bool(_call("sendMessage", body))


def set_webhook(url: str, secret_token: str = "", drop_pending: bool = False) -> bool:
    body: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "pre_checkout_query", "callback_query"],
        "drop_pending_updates": drop_pending,
    }
    if secret_token:
        body["secret_token"] = secret_token
    return bool(_call("setWebhook", body))


def delete_webhook() -> bool:
    return bool(_call("deleteWebhook", {"drop_pending_updates": False}))


def get_webhook_info() -> dict:
    return _call("getWebhookInfo", {}) or {}


def get_me() -> dict:
    return _call("getMe", {}) or {}


def send_webapp_button_message(chat_id: int, text: str, button_text: str) -> bool:
    markup = {"inline_keyboard": [[{"text": button_text, "web_app": {"url": settings.webapp_url}}]]}
    return send_message(chat_id, text, markup=markup)
