from pydantic import PostgresDsn, RedisDsn, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database (Supabase - async PostgreSQL)
    DB_URL: PostgresDsn

    # Cache/lock (Upstash Redis)
    REDIS_URL: RedisDsn

    # Authentication
    JWT_SECRET: str = Field(min_length=32)
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS - domains allowed to consume the API, comma-separated
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()