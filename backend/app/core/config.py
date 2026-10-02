"""
Amber Core Configuration Module.
Loads, validates, and exposes strongly-typed environment variables via Pydantic Settings.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 1. Project Info & Runtime Environment
    APP_NAME: str = "Amber"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # 2. Server & Networking
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "https://ambersre.xyz",
        "https://www.ambersre.xyz",
        "https://amber-frontend.pages.dev"
    ]
    # Development: SQLite (aiosqlite) | Production: PostgreSQL (asyncpg) + pgvector
    DATABASE_URL: str = "sqlite+aiosqlite:///./amber.db"

    # 4. Ephemeral State, Streaming & Distributed Caching (Redis)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = False

    # 5. Security & Authentication (JWT + Password Hashing)
    JWT_SECRET_KEY: str = "change_me_to_a_random_super_secret_key_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 6. LLM & Intelligence Provider Keys
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # 7. Telemetry & Observability (Langfuse)
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_ENABLED: bool = False

    # 8. Integrations & Notifications
    SLACK_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: Optional[str] = None  # e.g., "whatsapp:+14155238886"
    WHATSAPP_ALERT_TO: Optional[str] = None     # e.g., "919876543210" or "whatsapp:+919876543210"
    WHATSAPP_BRIDGE_URL: Optional[str] = None   # e.g., "http://localhost:3001" for self-hosted QR bridge
    DASHBOARD_URL: str = "https://ambersre.xyz"
    GMAIL_USER: str = "amber.incident@gmail.com"
    GMAIL_APP_PASSWORD: Optional[str] = None

    # 9. Monetization, Billing & Enterprise Licensing
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    AMBER_LICENSE_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Returns a cached singleton instance of the application settings."""
    return Settings()


settings: Settings = get_settings()