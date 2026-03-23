"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://tradecraft:tradecraft@localhost:5432/tradecraft"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Environment
    ENVIRONMENT: str = "development"

    # Broker settings (for future sprints)
    ZERODHA_API_KEY: Optional[str] = None
    ZERODHA_API_SECRET: Optional[str] = None
    ZERODHA_REDIRECT_URL: Optional[str] = None

    # Alert settings (for future sprints)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # Cognee memory API
    COGNEE_API_KEY: Optional[str] = None
    COGNEE_BASE_URL: str = "https://api.cognee.ai"

    # MiroFish integration (advisory-only sidecar)
    MIROFISH_ENABLED: bool = False
    MIROFISH_BASE_URL: str = "http://localhost:5001"
    MIROFISH_API_PREFIX: str = "/api"
    MIROFISH_TIMEOUT_SECONDS: float = 30.0
    MIROFISH_FAIL_OPEN: bool = True
    MIROFISH_API_KEY: Optional[str] = None

    # Paper trading defaults
    PAPER_INITIAL_CAPITAL: float = 500.0

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "production"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
