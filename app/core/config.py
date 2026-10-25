from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env holds human-managed secrets; .env.local holds values generated at setup time.
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    kapso_api_key: str
    kapso_phone_number_id: str
    kapso_webhook_secret: str
    kapso_api_base_url: str = "https://api.kapso.ai"
    public_base_url: str
    database_url: str = "sqlite:///db.sqlite3"

    # /admin is disabled unless this is set.
    admin_password: str | None = None

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, url: str) -> str:
        # Hosts like Railway hand out postgres:// or postgresql:// URLs; point them at psycopg (v3).
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
