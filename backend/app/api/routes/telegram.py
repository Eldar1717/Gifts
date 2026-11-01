"""Telegram bot webhook: pre-checkout, successful payments, /start."""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import get_db
from app.models import WebhookEvent
from app.services import notifications, telegram_bot
from app.services.orders import approve_pre_checkout
from app.services.payments import process_successful_payment

logger = get_logger(__name__)
router = APIRouter(tags=["telegram"])


WELCOME = (
    "<b>GIFT MARKET</b>\n\n"
    "Маркетплейс цифровых коллекционных подарков: покупайте, собирайте коллекции "
    "и перепродавайте предметы за Telegram Stars.\n\n"
    "Нажмите кнопку ниже, чтобы открыть приложение."
)


def _store_update(db: Session, update: dict) -> WebhookEvent | None:
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return None
    if db.scalar(select(WebhookEvent.id).where(WebhookEvent.update_id == update_id)):
        return None
    update_type = next(
        (key for key in ("message", "pre_checkout_query", "callback_query", "inline_query") if key in update),
        "unknown",
    )
    event = WebhookEvent(
        update_id=update_id,
        update_type=update_type,
        payload=json.dumps(update, ensure_ascii=False)[:50000],
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return event


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
        logger.warning("webhook.bad_secret")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="Invalid update")

    event = _store_update(db, update)
    if event is None:
        db.commit()
        return {"ok": True, "duplicate": True}

    error = ""
    try:
        if "pre_checkout_query" in update:
            query = update["pre_checkout_query"]
            ok, message = approve_pre_checkout(db, query)
            if ok:
                db.commit()
            try:
                telegram_bot.answer_pre_checkout_query(str(query.get("id")), ok, message)
            except telegram_bot.TelegramError:
                logger.exception("webhook.pre_checkout_answer_failed")
            logger.info(
                "webhook.pre_checkout", extra={"event": f"ok={ok} reason={message[:80]}"}
            )

        elif "message" in update and isinstance(update["message"], dict):
            message = update["message"]
            if "successful_payment" in message:
                outcome = process_successful_payment(db, message["successful_payment"])
                for notification_id in outcome.notifications:
                    background.add_task(notifications.deliver, notification_id)
                logger.info(
                    "webhook.payment",
                    extra={"order_id": outcome.order_id, "event": f"status={outcome.status}"},
                )
                if outcome.error:
                    error = outcome.error
            else:
                chat_id = message.get("chat", {}).get("id")
                text = (message.get("text") or "").strip().lower()
                if chat_id and text.startswith("/start"):
                    try:
                        if settings.webapp_url:
                            telegram_bot.send_webapp_button_message(
                                chat_id, WELCOME, "Открыть GIFT MARKET"
                            )
                        else:
                            telegram_bot.send_message(chat_id, WELCOME)
                    except telegram_bot.TelegramError:
                        logger.warning("webhook.welcome_failed")

        elif "callback_query" in update:
            callback = update["callback_query"]
            try:
                telegram_bot._call(  # noqa: SLF001 - internal helper is intentional here
                    "answerCallbackQuery", {"callback_query_id": callback.get("id")}
                )
            except telegram_bot.TelegramError:
                pass
    except Exception as exc:  # never let Telegram retry endlessly
        db.rollback()
        error = str(exc)[:500]
        logger.exception("webhook.processing_failed")
    finally:
        try:
            stored = db.scalar(select(WebhookEvent).where(WebhookEvent.update_id == event.update_id))
            if stored:
                stored.processed = not error
                stored.error = error
                stored.processed_at = utcnow()
                db.commit()
        except Exception:  # pragma: no cover
            db.rollback()
            logger.exception("webhook.event_update_failed")

    return {"ok": True}


@router.get("/telegram/webhook")
def webhook_health() -> dict:
    return {"ok": True, "configured": settings.bot_configured}
