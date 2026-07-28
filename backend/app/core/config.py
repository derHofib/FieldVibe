from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = (
        "postgresql+asyncpg://socialcrm:socialcrm@localhost:5432/socialcrm"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://socialcrm:socialcrm@localhost:5432/socialcrm"
    )

    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 14
    impersonation_token_expire_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:5173"]

    first_super_admin_email: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
