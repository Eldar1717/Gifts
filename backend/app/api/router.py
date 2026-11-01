"""API router assembly."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import account, admin, market, public, telegram
from app.core.config import settings
from app.db.session import get_db

api_router = APIRouter()
rest_router = APIRouter()


@rest_router.get("/health", tags=["system"])
def health() -> dict:
    return {"ok": True, "service": "gift-market-api", "env": settings.env}


@rest_router.get("/health/ready", tags=["system"])
def readiness(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"ok": True, "database": db.get_bind().dialect.name}


rest_router.include_router(public.router)
rest_router.include_router(account.router)
rest_router.include_router(market.router)
rest_router.include_router(admin.router)
rest_router.include_router(telegram.router)

api_router.include_router(rest_router)
