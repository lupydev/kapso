from functools import lru_cache

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
    invoice_amount_cents: int = 5000000
    invoice_currency: str = "COP"


@lru_cache
def get_settings() -> Settings:
    return Settings()
