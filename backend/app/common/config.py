from functools import lru_cache
from zoneinfo import ZoneInfo
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationError, model_validator, AnyUrl


class Settings(BaseSettings):
    """Application settings with runtime validation and helpful defaults.

    Notes:
    - `ALLOWED_ORIGINS` should be set as a JSON array in the environment when
      deploying (e.g. ALLOWED_ORIGINS=["https://app.example.com"]). For local
      development the defaults include localhost entries.
    - `TIMEZONE` is validated against the system zoneinfo database.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AI_MULTI_ASSET_BOT"
    APP_PORT: int = 8100
    FRONTEND_PORT: int = 5180

    DATABASE_URL: str = "postgresql://bot_user:changeme@postgres:5432/ai_multiasset_bot"
    REDIS_URL: str = "redis://redis:6379/0"

    POSTGRES_DB: str = "ai_multiasset_bot"
    POSTGRES_USER: str = "bot_user"
    POSTGRES_PASSWORD: str = "changeme"

    TIMEZONE: str = "America/New_York"

    DISCORD_BOT_TOKEN: str = ""
    DISCORD_TRADING_CHANNEL_ID: str = "0"
    DISCORD_USER_ID: str = "0"
    DISCORD_ALLOWED_ROLE_IDS: str = ""
    DISCORD_DECISION_MAX_AGE_SECONDS: int = 900
    DISCORD_REQUIRE_DECISION_TIMESTAMP: bool = True

    KRAKEN_API_KEY: str = ""
    KRAKEN_API_SECRET: str = ""

    TRADIER_ACCESS_TOKEN: str = ""
    TRADIER_ACCOUNT_ID: str = ""

    ADMIN_API_TOKEN: str = "changeme_admin_token"

    # Explicit list of origins the browser is allowed to call from.
    # In .env set as a JSON array: ALLOWED_ORIGINS=["https://app.example.com"]
    # Defaults cover local development only.
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5180",
        "http://127.0.0.1:5180",
    ]

    CRYPTO_MONITOR_INTERVAL: int = 15
    STOCK_MONITOR_INTERVAL: int = 15
    EXIT_WORKER_INTERVAL: int = 30

    # ------------------------------------------------------------------
    # Runtime validation hooks
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        # Validate timezone string maps to a known ZoneInfo
        try:
            _ = ZoneInfo(self.TIMEZONE)
        except Exception as exc:
            raise ValidationError([f"Invalid TIMEZONE: {self.TIMEZONE}"])

        # Validate ports
        if not (1 <= self.APP_PORT <= 65535):
            raise ValidationError([f"APP_PORT out of range: {self.APP_PORT}"])
        if not (1 <= self.FRONTEND_PORT <= 65535):
            raise ValidationError([f"FRONTEND_PORT out of range: {self.FRONTEND_PORT}"])

        # Ensure ALLOWED_ORIGINS is a list of non-empty URL-like strings.
        cleaned: list[str] = []
        for v in (self.ALLOWED_ORIGINS or []):
            if not isinstance(v, str) or not v.strip():
                continue
            # Basic scheme validation: allow http(s) only for browser origins
            if not (v.startswith("http://") or v.startswith("https://")):
                # allow localhost entries without scheme for convenience
                if v.startswith("localhost") or v.startswith("127.0.0.1"):
                    cleaned.append("http://" + v)
                    continue
                raise ValidationError([f"ALLOWED_ORIGINS entries must start with http:// or https://: {v}"])
            cleaned.append(v.rstrip("/"))
        self.ALLOWED_ORIGINS = cleaned or ["http://localhost:5180", "http://127.0.0.1:5180"]

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
