"""In-app notifications plus Telegram delivery in background tasks."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import NotificationType
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models import Notification, User
from app.services import telegram_bot

logger = get_logger(__name__)


def create_notification(
    db: Session,
    user: User,
    *,
    type: NotificationType,
    title: str,
    body: str = "",
    payload: dict | None = None,
    telegram: bool = True,
) -> Notification:
    """Persist an in-app notification. Telegram delivery happens after commit."""
    row = Notification(
        user_id=user.id,
        type=type.value,
        title=title[:120],
        body=body[:2000],
        payload=json.dumps(payload or {}, ensure_ascii=False),
        telegram_sent_at=None if telegram else utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def deliver(notification_id: int) -> None:
    """Background task: push one notification to the user's Telegram chat."""
    db = SessionLocal()
    try:
        notification = db.get(Notification, notification_id)
        if notification is None or notification.telegram_sent_at is not None:
            return
        user = db.get(User, notification.user_id)
        if user is None:
            return
        text = f"<b>{notification.title}</b>"
        if notification.body:
            text += f"\n\n{notification.body}"
        if settings.webapp_url:
            markup = {
                "inline_keyboard": [
                    [{"text": "Открыть GIFT MARKET", "web_app": {"url": settings.webapp_url}}]
                ]
            }
        else:
            markup = None
        try:
            telegram_bot.send_message(user.telegram_id, text, markup=markup)
            notification.telegram_sent_at = utcnow()
        except telegram_bot.TelegramError as exc:
            notification.telegram_error = str(exc)[:500]
            logger.warning("notification.telegram_failed", extra={"user_id": user.id})
        db.commit()
    except Exception:  # pragma: no cover - background safety net
        db.rollback()
        logger.exception("notification.deliver_failed")
    finally:
        db.close()


def deliver_many(notification_ids: list[int]) -> None:
    for notification_id in notification_ids:
        deliver(notification_id)


def notify(
    db: Session,
    user: User,
    **kwargs,
) -> Notification | None:
    """Create a notification honouring the user's preferences.

    Sales/purchase notices are always stored in-app; marketing-style notices
    respect ``notify_market``.
    """
    type_ = kwargs.get("type")
    if type_ == NotificationType.OFFER and not user.allow_offers:
        return None
    if type_ in {
        NotificationType.SALE,
        NotificationType.SELLER_CREDIT,
        NotificationType.LISTING_CREATED,
        NotificationType.PAYOUT,
    } and not user.notify_sales:
        # Still record in-app for the history, but skip the Telegram push.
        kwargs["telegram"] = False
    if type_ == NotificationType.SYSTEM and not user.notify_market:
        kwargs["telegram"] = False
    return create_notification(db, user, **kwargs)


def mark_read(db: Session, user_id: int, notification_ids: list[int] | None = None) -> int:
    query = db.query(Notification).filter(Notification.user_id == user_id, Notification.is_read.is_(False))
    if notification_ids:
        query = query.filter(Notification.id.in_(notification_ids))
    count = query.update({Notification.is_read: True}, synchronize_session=False)
    return int(count)


def unread_count(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .count()
    )


def to_epoch(value: datetime | None) -> int | None:
    return int(value.timestamp()) if value else None
