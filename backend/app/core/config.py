from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str  # postgresql+asyncpg://...

    # ── JWT ─────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ────────────────────────────────────────────────────────────────
    # Comma-separated in .env; parsed as a list here
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── App ─────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"


settings = Settings()
