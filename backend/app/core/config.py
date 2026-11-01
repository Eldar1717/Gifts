"""Application configuration.

Every value is read from environment variables (or a local ``.env`` file).
Production guards are enforced at import time so a misconfigured deployment
fails fast instead of running insecurely.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- General ---------------------------------------------------------
    app_name: str = "GIFT MARKET API"
    api_prefix: str = "/api"
    env: Environment = "development"
    log_level: str = "INFO"

    # --- Database --------------------------------------------------------
    database_url: str = "sqlite:///./gift_market.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Telegram --------------------------------------------------------
    bot_token: str = ""
    bot_username: str = ""
    webapp_url: str = ""
    public_base_url: str = ""
    webhook_secret: str = ""
    init_data_max_age_seconds: int = 86400

    # --- Access control --------------------------------------------------
    admin_telegram_ids: str = ""
    dev_auth: bool = False
    demo_telegram_id: int = 900000001

    # --- CORS / proxy ----------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trusted_hosts: str = "*"

    # --- Marketplace defaults (DB settings can override) -----------------
    commission_percent: int = Field(default=10, ge=0, le=50)
    min_listing_price: int = Field(default=10, ge=1)
    max_listing_price: int = Field(default=100_000, ge=1)
    balance_hold_hours: float = Field(default=72.0, ge=0)
    listing_reservation_minutes: int = Field(default=20, ge=1, le=1440)
    cleanup_interval_seconds: int = Field(default=60, ge=5)

    # --- Rate limits (requests / window seconds) -------------------------
    rate_limit_auth: str = "60/60"
    rate_limit_write: str = "60/60"
    rate_limit_checkout: str = "15/60"
    rate_limit_read: str = "300/60"

    # --- TON integration (optional) --------------------------------------
    tonapi_base_url: str = "https://tonapi.io"
    tonapi_key: str = ""

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Render/Heroku style URLs use the deprecated ``postgres://`` scheme.
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.env == "production":
            problems: list[str] = []
            if self.dev_auth:
                problems.append("DEV_AUTH must be disabled in production")
            if not self.bot_token:
                problems.append("BOT_TOKEN is required in production")
            if not self.database_url.startswith("postgresql"):
                problems.append("DATABASE_URL must point to PostgreSQL in production")
            if not self.webhook_secret:
                problems.append("WEBHOOK_SECRET is required in production")
            if "*" in self.cors_origin_list:
                problems.append("CORS_ORIGINS must be explicit in production")
            if problems:
                raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self

    # --- Derived helpers -------------------------------------------------
    @property
    def admin_ids(self) -> set[int]:
        return {
            int(part.strip())
            for part in self.admin_telegram_ids.split(",")
            if part.strip().lstrip("-").isdigit()
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def dev_mode_enabled(self) -> bool:
        """Dev auth / payment simulator is available only outside production."""
        return self.dev_auth and not self.is_production

    @property
    def bot_configured(self) -> bool:
        return bool(self.bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
