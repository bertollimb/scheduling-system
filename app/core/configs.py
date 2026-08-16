from pydantic import PostgresDsn, RedisDsn, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
   
    DB_URL: PostgresDsn

    REDIS_URL: RedisDsn

    JWT_SECRET: str = Field(min_length=32)
    """
    Open the Python

    import secrets

    token: str = secrets.token_urlsafe(32)

    """
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra='ignore'
    )

settings = Settings()

