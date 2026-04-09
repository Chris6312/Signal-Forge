from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
