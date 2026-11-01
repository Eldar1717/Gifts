"""FastAPI dependencies: Telegram authentication, roles, request context."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import AdminRole
from app.core.security import AuthError, TelegramIdentity, validate_init_data
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AdminUser, User


def _sync_admin_role(db: Session, user: User) -> str | None:
    env_admin = user.telegram_id in settings.admin_ids
    admin = db.scalar(select(AdminUser).where(AdminUser.user_id == user.id))
    if env_admin:
        if admin is None:
            admin = AdminUser(user_id=user.id, role=AdminRole.SUPERADMIN.value, is_active=True)
            db.add(admin)
        elif not admin.is_active:
            admin.is_active = True
        user.is_admin = True
        return admin.role
    if admin and admin.is_active:
        user.is_admin = True
        return admin.role
    user.is_admin = False
    return None


def _upsert_user(db: Session, identity: TelegramIdentity) -> User:
    user = db.scalar(select(User).where(User.telegram_id == identity.telegram_id))
    if user is None:
        user = User(
            telegram_id=identity.telegram_id,
            username=identity.username,
            first_name=identity.first_name,
            last_name=identity.last_name,
            photo_url=identity.photo_url,
            language_code=identity.language_code,
            is_premium=identity.is_premium,
        )
        db.add(user)
        db.flush()
    else:
        user.username = identity.username or user.username
        user.first_name = identity.first_name or user.first_name
        user.last_name = identity.last_name or user.last_name
        user.photo_url = identity.photo_url or user.photo_url
        user.language_code = identity.language_code or user.language_code
        user.is_premium = identity.is_premium
        user.last_seen_at = utcnow()
    _sync_admin_role(db, user)
    db.commit()
    db.refresh(user)
    return user


def _dev_identity(request: Request) -> TelegramIdentity:
    raw_id = request.headers.get("x-dev-telegram-id")
    telegram_id = settings.demo_telegram_id
    if raw_id and raw_id.lstrip("-").isdigit():
        telegram_id = int(raw_id)
    if telegram_id == settings.demo_telegram_id:
        username, first_name = "demo_collector", "Demo"
    else:
        username, first_name = f"user_{telegram_id}", f"User {telegram_id}"
    return TelegramIdentity(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name="",
        photo_url="",
        language_code="ru",
        is_premium=False,
        auth_date=0,
        raw={"id": telegram_id, "username": username},
    )


def _resolve_identity(request: Request, authorization: str | None) -> TelegramIdentity:
    if authorization and authorization.lower().startswith("tma "):
        return validate_init_data(authorization[4:].strip())
    if settings.dev_mode_enabled:
        return _dev_identity(request)
    raise AuthError("Откройте приложение через Telegram")


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    identity = _resolve_identity(request, authorization)
    user = _upsert_user(db, identity)
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт заблокирован. Обратитесь в поддержку.",
        )
    request.state.user_id = user.id
    return user


def get_optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    if not authorization and not settings.dev_mode_enabled:
        return None
    try:
        return get_current_user(request, authorization, db)
    except HTTPException:
        return None


def require_admin(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    admin = db.scalar(select(AdminUser).where(AdminUser.user_id == user.id))
    if not (user.is_admin and admin and admin.is_active):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    request.state.admin_role = admin.role
    return user


def require_superadmin(
    user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> User:
    admin = db.scalar(select(AdminUser).where(AdminUser.user_id == user.id))
    if admin is None or admin.role not in {AdminRole.SUPERADMIN.value, AdminRole.ADMIN.value}:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user


def admin_role(user: User, db: Session) -> str | None:
    admin = db.scalar(select(AdminUser).where(AdminUser.user_id == user.id))
    return admin.role if admin and admin.is_active else None
